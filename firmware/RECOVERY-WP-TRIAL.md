# Corrected recovery trial

28 October2026. The owner authorized correcting and physically testing recovery, then trying Apple battery reporting only after recovery works.

## Observed first trial

The14528-byte neutral trial was staged and read back, and SS0 activation verified. Startup checks then found SS0 still valid and selecting4000, SS100 valid and selecting8000, and the exact working A86 extension/methods running from8000. Typing works. Thus the failure redirect was physically observed, while invalidation and automatic next-boot rollback were not successful. The Apple profile has not been installed.

The first controller model omitted the board's write-protection behavior. Actual ROM pre-DS initialization sets callback200A18 to17541, but selector200A02 remainsFF until original DS config A7 loads. The guard was before A7 and bypassed that callback. The original writer's callback saves GPIO configuration, drives configured GPIO2/0 low for writing, and restores the configuration immediately after the byte transaction. An EEPROM with WP high can ACK but ignore programming. The code and observations support this explanation; physical pin continuity remains unmeasured.

## Correction

Separate source `research/radio_one_boot_guard_wp.S` and builder `firmware/build_radio_wp_trial.py` preserve the failed source/images. The corrected prefix applies the exact original20-byte A7 configuration first. The guard verifies selector40 and callback17541, calls the original GPIO callback with0 before the bounded async write, preserves the completion result, and calls it with1 on completion, error or timeout before ACK polling/readback/redirect. The normal original A7 remains later in the DS, giving the same final configuration.

The guard remains236bytes; the complete neutral image is14595bytes, SHA256 `9994716588b3c9309c219c807d6c99fb797341d8229077d59c5ab64c27b2d5ff`. The Apple one-boot image built with the identical corrected prefix is15783bytes, SHA256 `a9e1a7af26709794e3023518e0f192f60c0c8dbfe72ce4c9f4ba93715ffdb7a6`; it remains offline pending physical acceptance of neutral recovery.

## Staging safeguards

`installers/radio_wp_trial.py` expects the exact completed first trial with A86 currently running from8000. It saves a fresh full64KiB read before strict comparison. It first invalidates SS0 and verifies it, leaving the already verified SS100/A86 as the sole boot choice. Only then can it replace DS4000. It does not rewrite SS100, the SS0 body, original or working firmware banks, or any pairing/settings. It verifies all staged bytes and retained banks, then commits SS0 byte0 last. All hardware updating remains disabled by default; the pinned admin-helper mode is `--apply-wp-trial`.

The root helper still claims/releases/validates first, reclaims, permanently drops privileges, then saves/backups/enables. Its isolated source loading checks base, original preflight dependency and corrected trial separately. The older modes remain predecessor-specific.

Six offline staging methods pass, including all14597 completed-byte interruption states, lost acknowledgments, exact predecessor rejection, write boundaries and live VS preservation. Nine corrected boot methods execute actual scatter, full pre-DS init, A7 parser, GPIO helpers and async I2C setup/status against modeled protected EEPROM. They reproduce the old failure and test correction, eight failure modes, callback mismatch, watchdog service and original pin configurations. Input-mode restoration correctly releases the pin; restoring an irrelevant output latch in input mode is not required by the original ROM routine.

The GPIO-to-WP wire, EEPROM behavior and controller completion remain models in those tests. Physical bus failure is still outside software guarantees. The next step is the neutral hardware trial, not an Apple identity/profile change.

## Physical acceptance

Both stages now passed on the owner's keyboard. The `trial` check observed SS0 invalid, current DS4000, exact A86 extension/methods and working typing. After the owner unplugged USB and switched fully OFF for10seconds, `fallback` observed current DS8000 and the same valid fallback/invalid trial headers, again with working typing. See `artifacts/k2-initial-release/radio-wp-{trial,fallback}-verification.json`. The Apple one-boot experiment can now proceed under the owner's existing authorization; [trial details](APPLE-NATIVE-ONE-BOOT.md).

After the corrected neutral installer finishes and the keyboard reconnects, the read-only command `installers/verify_radio_wp_trial.py trial` must confirm invalid SS0 selecting4000, valid SS100 selecting8000, current DS4000, and exact working A86 methods/extension. Typing must work.

Only after that passes, power fully off without USB for10seconds and restart Bluetooth. The read-only `fallback` check must show DS8000 with the same invalid trial/valid backup headers and working typing. Both stages save separate sanitized results. Only those observed successes clear the Apple one-boot experiment.
