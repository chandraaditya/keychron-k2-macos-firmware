# Apple native battery one-boot experiment

28 October2026. The corrected neutral guard is now physically accepted. The owner confirmed typing in both states. Read-only `radio-wp-trial-verification.json` confirms DS4000 with invalidated SS0 and exact A86 methods; after unplugging USB and a full10-second OFF interval, `radio-wp-fallback-verification.json` confirms DS8000 with the same invalid trial header and valid A86 backup. These are observed results, not emulator predictions.

## Experimental image

`private/candidates/radio-apple-wp-one-boot/dynamic-section.bin` is15783bytes, SHA256 `a9e1a7af26709794e3023518e0f192f60c0c8dbfe72ce4c9f4ba93715ffdb7a6`. Its first three records—original A7, corrected236-byte guard load and invocation—are byte-identical to the physically successful neutral trial. Current A86 at8000 and original firmware at3C0 remain the fallback/reference targets.

The A87 profile advertises Bluetooth-company vendor004C, product0267, source1 and a429-byte grouped descriptor. A marker enables separate host interfaces. One outer keyboard collection retains all323 original report bytes together; a separate management collection retains the83 observed Apple bytes, including Input90. BF provides the full1053-byte SDP blob without relocating the original application. Feature34 returns77bytes/version3 with the keyboard's own address; Input90 returns3bytes with current estimated percentage. Both GET and connection/change notifications are implemented; normal changes retain60-second throttling. Standard report3 and original keyboard/media/system/diagnostic handlers remain.

Status flags and Feature34 firmware-version fields remain zero. Optional Apple startup requests are unsupported. Actual Bluetooth host preprocessing, driver attachment and native widget behavior are the experiment; these are not implied by matching report bytes or IDs. The original voltage-based charge estimate remains, including its charging/load sensitivity.

## Installer and recovery

`installers/radio_apple_trial.py` requires both exact corrected physical recovery results before the native device can open, then rechecks them and the live A86 code/methods. It expects the exact completed neutral image with invalid SS0 and current DS8000. A fresh full64KiB backup is saved before strict comparison. Pairing/VS may change as before; other storage changes cause a saved-capture refusal.

Only DS4000 and the single SS0 activation byte can be written. SS0 is already invalid during staging, so interrupted writes select retained A86. The image and all protected banks/headers/settings are verified before final SS0 activation. No SS100, SS0-body, active/original bank, pairing or metadata writes are included. The admin helper's separate `--apply-apple-trial` source pins include all dependencies; root is permanently dropped before backup/enable. Updating remains disabled by default.

Seven installer tests pass, including15784 completed-byte cut states, exact predecessor checks, lost-ACK stop and both physical-proof requirements. Component/boot tests and independent Astra review match the candidate/prefix/report contract. The isolated system interpreter's checked dependency load passed with both real recovery proofs and without opening hardware.

## Observations and acceptance

Initial physical Apple trial: staging/activation transaction succeeded. Owner-run readback verified A87 identity, exact572-byte extension, all methods, DS4000 and invalidated SS0 with A86 fallback8000. The radio's cached1053-byte SDP blob exactly matched the grouped fixture. Input90 returned87/status0 and typing worked. macOS still published the original05AC/024F/source2 identity and323-byte descriptor. Direct Feature34 returned e00002bc, and no address-matched native management service was found. This establishes active firmware and a stale published host profile; the cause of Feature34 failure is still unproven. Initial results are preserved in `radio-apple-trial-initial-cached-profile-verification.json`.

A powered-on fresh pairing in existing slot1 is the next bounded test. The exact Sonix V2 1.13 long-profile-key path queues pairing command89; the reviewed radio89 handler enters its pairing/disconnect/scanning state rather than the watchdog reset routine. Host behavior still requires observing A87 after pairing. The `--runtime-only` checker skips direct90/34 queries and saves a separate result, preserving first observations. It records radio SDP correctness, actual host identity/descriptor, native service association and current pairing slot before any further report diagnosis.

`installers/verify_radio_apple_trial.py` is read-only and takes no arguments. It uses Bluetooth Product=Keychron K2 plus the original B2 diagnostic element, without restricting the old vendor ID. Before interpreting data it verifies the exact A87 marker,572-byte extension hash, constructor hook, all15 shadow methods, current DS4000 and both rollback headers. It records actual published VID/source/PID and report-descriptor size/hash; this distinguishes old host-cached identity from the firmware state.

It queries Input90 and Feature34 without exclusive claim, then associates AppleDeviceManagementHIDEventService by the exact own address read from the battery object. Only sanitized service/battery results are saved; raw address, serial and Feature34 bytes are neither printed nor saved. Four offline verifier tests cover runtime corruption, exact native address association and GET type/length/failure behavior. The widget still requires owner observation.

Observe initial attachment before requesting a fresh pairing: an existing bond can retain the old05AC/024F identity/323-byte descriptor. A cache outcome does not by itself mean the A87 code or Apple report framing failed. If the host changes the advertised Product or hides the diagnostic collection, the reader stops; use registry metadata to identify the state before any additional device requests.

Keep the trial powered for observation. A subsequent full power cycle selects A86; fresh pairing may be necessary to clear the experimental host profile after changing identity. Native display, useful low-battery behavior and long runtime are not yet accepted. Making the profile persistent is a later reviewed step after an actual successful trial.
