from d3_assignment_planner import IdentityCommitmentState, TargetTrack


def committed_target_track(*args, **kwargs) -> TargetTrack:
    """Build an explicitly identity-committed target for non-admission tests."""

    kwargs.setdefault(
        "identity_commitment_state",
        IdentityCommitmentState.COMMITTED,
    )
    return TargetTrack(*args, **kwargs)
