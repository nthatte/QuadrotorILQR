#include "src/ilqr.hh"

#include <gtest/gtest.h>
#include <manif/impl/se3/SE3.h>

#include "dynamics.hh"
#include "trajectory.hh"

namespace src {

using State = LieDynamics::State;
using Control = LieDynamics::Control;
using DynamicsDifferentials = LieDynamics::DynamicsDifferentials;
using ILQRSolver = ILQR<LieDynamics>;
using CostFunc = CostFunction<LieDynamics>;

class ILQRFixture : public ::testing::Test {
 protected:
  ILQRFixture() {
    current_traj_ =
        Trajectory<LieDynamics>{N_,
                                {.time_s = 0.0,
                                 .state = LieDynamics::State::Identity(),
                                 .control = LieDynamics::Control::Identity()}};
    auto time_s = 0.0;
    for (auto &pt : current_traj_) {
      pt.time_s = time_s;
      time_s += dt_s_;
    }

    Control::Tangent delta_u = Control::Tangent::Zero();
    delta_u.coeffs()(0) = 1.0;  // delta-x-pos
    ctrl_update_traj_ = ILQRSolver::ControlUpdateTrajectory{
        N_, ILQRSolver::ControlUpdate{
                .ff_update = delta_u,
                .feedback = ILQRSolver::FeedbackGains::Zero()}};
  }

  size_t N_ = 3;
  double dt_s_ = 0.1;
  Trajectory<LieDynamics> current_traj_;
  ILQRSolver::ControlUpdateTrajectory ctrl_update_traj_;

  // create cost function
  CostFunc::CostHessianStateState Q_ =
      CostFunc::CostHessianStateState::Identity();
  CostFunc::CostHessianControlControl R_ =
      CostFunc::CostHessianStateState::Identity();

  ILQRSolver ilqr_{
      CostFunc{Q_, R_, {N_, State::Identity()}, {N_, Control::Identity()}},
      LineSearchParams{0.5, 0.5}};
};

TEST_F(ILQRFixture, ForwardPassSimulatesTrajectory) {
  // expected new trajectory
  Trajectory<LieDynamics> new_traj_expected{
      {.time_s = 0.0,
       .state = LieDynamics::State::Identity(),
       .control =
           LieDynamics::Control{{1.0, 0.0, 0.0}, manif::SO3d::Identity()}},
      {.time_s = dt_s_,
       .state = LieDynamics::State{{1.0, 0.0, 0.0}, manif::SO3d::Identity()},
       .control =
           LieDynamics::Control{{1.0, 0.0, 0.0}, manif::SO3d::Identity()}},
      {.time_s = 2 * dt_s_,
       .state = LieDynamics::State{{2.0, 0.0, 0.0}, manif::SO3d::Identity()},
       .control =
           LieDynamics::Control{{1.0, 0.0, 0.0}, manif::SO3d::Identity()}}};

  const auto new_traj =
      ilqr_.forward_pass(current_traj_, ctrl_update_traj_).first;

  EXPECT_EQ(new_traj, new_traj_expected);
}

TEST_F(ILQRFixture, ForwardPassCalculatesCorrectCost) {
  const auto cost = ilqr_.forward_pass(current_traj_, ctrl_update_traj_).second;

  const auto expected_cost = 1.0 + 2.0 * 2.0 + 1.0 * 3;

  EXPECT_EQ(cost, expected_cost);
}

TEST_F(ILQRFixture, ForwardPassCalculatesDifferentialsIfRequested) {
  std::vector<ILQRSolver::OptDiffs> opt_diffs{N_};
  ilqr_.forward_pass(current_traj_, ctrl_update_traj_, 1.0, &opt_diffs);

  int i = 0;
  for (const auto &diffs : opt_diffs) {
    if (i++ == 0) {
      EXPECT_EQ(diffs.cost_diffs.x, CostFunc::CostJacobianState::Zero());
    } else {
      EXPECT_NE(diffs.cost_diffs.x, CostFunc::CostJacobianState::Zero());
    }
    EXPECT_NE(diffs.cost_diffs.u, CostFunc::CostJacobianControl::Zero());
    EXPECT_NE(diffs.cost_diffs.xx, CostFunc::CostHessianStateState::Zero());
    EXPECT_NE(diffs.cost_diffs.uu, CostFunc::CostHessianControlControl::Zero());
    EXPECT_EQ(diffs.cost_diffs.xu, CostFunc::CostHessianStateControl::Zero());

    EXPECT_NE(diffs.dynamics_diffs.J_x, State::Jacobian::Zero());
    EXPECT_NE(diffs.dynamics_diffs.J_u, Control::Jacobian::Zero());
  }
}

TEST_F(ILQRFixture, BackwardPassReturnsZeroUpdateIfZeroGradient) {
  constexpr size_t num_pts = 4;
  std::vector<ILQRSolver::OptDiffs> diffs{
      num_pts, ILQRSolver::OptDiffs{
                   .dynamics_diffs =
                       DynamicsDifferentials{.J_x = State::Jacobian::Zero(),
                                             .J_u = Control::Jacobian::Zero()},
                   .cost_diffs = CostFunc::CostDifferentials{
                       .x = CostFunc::CostJacobianState::Zero(),
                       .u = CostFunc::CostJacobianControl::Zero(),
                       .xx = CostFunc::CostHessianStateState::Identity(),
                       .uu = CostFunc::CostHessianControlControl::Identity(),
                       .xu = CostFunc::CostHessianStateControl::Zero(),
                   }}};

  const auto [ctrl_traj_update, expected_cost_reduction] =
      ilqr_.backwards_pass(diffs);

  EXPECT_EQ(ctrl_traj_update.size(), num_pts);
  EXPECT_EQ(expected_cost_reduction, 0.0);
  for (const auto &ctrl_update : ctrl_traj_update) {
    EXPECT_EQ(ctrl_update.ff_update, Control::Tangent::Zero());
    EXPECT_EQ(ctrl_update.feedback, ILQRSolver::FeedbackGains::Zero());
  }
}

TEST_F(ILQRFixture,
       BackwardsPassExpectedValueReductionIsNegativeIfReductionPossible) {
  std::vector<ILQRSolver::OptDiffs> opt_diffs{N_};
  ilqr_.forward_pass(current_traj_, ctrl_update_traj_, 1.0, &opt_diffs);

  const auto expected_cost_reduction = ilqr_.backwards_pass(opt_diffs).second;

  EXPECT_LT(expected_cost_reduction, 0.0);
}
}  // namespace src