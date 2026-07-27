# Stateful BIOS Control

Use this reference for firmware observation, cartography, navigation, mutation,
save, or recovery. The semantic tools maintain the BIOS graph and current
position; they do not turn raw KVM input into a policy-gated channel.

## Observe and synchronize

Start with `bios_observe_state`. Treat its parsed state as evidence to verify
against the visible screen, especially before a mutation or save. If the state
is unknown or ambiguous, stop and obtain a clearer observation instead of
guessing a menu path.

Use `kvm_match_screen` or `kvm_vlm_parse` only for targeted perception or
diagnosis when the semantic workflow reports an unmatched screen. They are
observation tools, not navigators.

## Map or navigate

Use `bios_crawl_step` for a single inspectable cartography transition. Use
`bios_crawl_region(max_depth=...)` only for a bounded region and review its
block or failure result before continuing.

Use `bios_navigate_to(target_node_id=...)` only when the requested destination
exists in the stored graph. After navigation, call `bios_observe_state` and
confirm the expected screen and selected control before proposing a change.

## Change and verify

1. Call `bios_propose_setting_change(capability_id=..., desired_value=...)` with
   the exact capability and desired value.
2. Confirm the proposal matches the requested setting and current target.
3. Call `bios_apply_setting_change(capability_id=..., desired_value=...)` once.
4. Re-observe and verify the visible new value. Do not stage another variable in
   the same experiment.
5. Call `bios_save_and_reboot` only when saving is explicitly in scope and the
   staged value has been verified.

Tool annotations, bounded paths, blocklist detection, and visual verification
are safeguards, but no approval-token or hidden policy engine exists.

## Recover

Use `bios_abort_and_recover` when the semantic workflow can safely back out. If
input failed or was interrupted, call `kvm_release_all`, then
`bios_observe_state`. Do not replay the prior sequence until the actual screen
and focus are known.

Use `bios_export_trace` when the user requests evidence or the workflow needs a
replayable diagnostic record. Disconnect through the general Comet operations
workflow when no continuing observation is needed.
