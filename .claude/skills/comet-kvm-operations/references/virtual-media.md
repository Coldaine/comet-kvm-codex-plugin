# Virtual Media

Read this file when the task involves an ISO, rescue image, installer, firmware
image, or virtual USB media.

## Inspect and stage media

Start with `comet_media_state`. Determine the selected image, connected state,
mode, and whether the requested image already exists.

Reuse a matching verified image. Otherwise use `comet_media_upload` for a local
file the user placed in scope, or `comet_media_fetch` for a user-approved URL
reachable by the Comet. Do not upload unrelated local files or make the Comet
fetch an untrusted URL.

## Mount and boot

Use `comet_media_mount` in read-only CD-ROM mode for ISO installers and rescue
media unless the workflow requires writable flash media. Inspect media state
again after mounting.

Prefer a one-time boot menu, then a temporary firmware boot override when
supported. Use a persistent BIOS boot-order change only when the user explicitly
wants firmware configuration changed, and hand that portion to
`comet-bios-triage`.

Reboot or reset only after the media state is verified. Observe POST and confirm
that the requested installer or rescue environment loaded.

## Clean up

Call `comet_media_unmount` when the workflow no longer needs the media unless
the user asked to leave it attached. Call `comet_media_remove` only when the
user requests deletion or the image is known to be temporary. Use
`comet_media_reset` only to recover a stuck media subsystem, followed by a fresh
state check.

Report the image, mount mode, connected state, boot result, and any media left
attached.
