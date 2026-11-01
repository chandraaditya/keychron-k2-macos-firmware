# A90: repair the confirmed long-reply drop

28 October2026. Staging was attempted and interrupted; **A90 never activated**.

## Interrupted staging and confirmed fallback

The owner ran the isolated MTU updater. Its journal saved the full fresh backup and passed preflight, then verified8016 staged bytes before the process received SIGALRM during the next14-byte write at5F50. There is no ready-to-commit or commit event. The host per-request alarm is3 seconds; the underlying reason the call did not return in that interval remains unknown. Do not simply extend the timeout or retry against this changed runtime.

Read-only checks afterward verify exact A86 runtime/methods at8000, updater inactive, SS0 invalid, and the retained A86 SS100 header. The owner confirms normal Bluetooth typing including Shift/Backspace. The final uncertain14-byte range now matches the saved backup. Every attempted write payload in this prefix was identical to the previous A89 image; no new A90-specific bytes were reached. All write intents were confined to the inactive bank. The guard therefore prevented activation of an unfinished trial. No automatic retry, reset, pairing change or firmware write was performed during diagnosis.

Evidence: `artifacts/k2-initial-release/A90-interrupted-update-runtime-check.json` and `A90-interrupted-update-review.json`; private durable journal `radio-1793176512582940000.jsonl` retains the write intents and backup. The installer below still requires exact active A89, so it is **not a valid retry command from the current A86 state**.

The following sections record the reviewed candidate and the pre-attempt plan; they are not evidence of successful installation.

## Reviewed recovery installer from A86

`installers/radio_mtu_recovery.py` deliberately starts from exact active A86 at8000 with SS0 invalid and SS100 matching the retained fallback. It accepts the exact cached Apple raw maintenance interface or the original B2 collection inside the existing Product/Transport match, then validates live A86 code/methods/updater state and boot headers. The interrupted journal and saved backup must show no commitment and only attempted payloads identical to the old prefix.

The unchanged reviewed A90 candidate differs from the pinned A89 storage baseline in only12 application bytes, across seven spans. The recovery plan's write allowlist covers only these exact spans and final SS0 byte0, and verifies the actual payload bytes against the candidate. It saves a new full backup and compares the entire EEPROM outside the legitimate VS area before enabling updates. Unexpected partial changes or metadata drift reject before enable. It writes only the12 differences, then verifies the complete resulting A90 image and the original/A86 banks, headers, VS and metadata before the single activation byte.

No timeout is increased: the native request alarm remains3 seconds, conservative watchdog margin6 seconds and device inactivity reset10 seconds. No failed call is replayed. Durable request start/completion events now distinguish SET74, read-setup SET71 and GET72, including actual read address/count, during writes and full verification. This repairs the prior diagnostic ambiguity; it does not establish the original timeout's cause or guarantee another timeout cannot occur.

Twelve recovery/observer tests pass, covering13 completed-byte cut points, every write failing before/after acknowledgment, strict runtime/storage rejection, full-readback failure before commitment, exact payload restrictions, protected storage preservation, native request records and bulk-verification contexts. Eight admin-helper tests pass and the isolated pinned nine-module loader succeeds without opening a device. Astra independently reviewed the sparse recovery transaction and found no blocking defect; its requested fuller verification logging was subsequently added and tested. A final live read-only check reconfirmed A86 and both recovery headers, with updates disabled.

Owner-operated command for this reviewed recovery transaction, Bluetooth selected and USB power connected:

```sh
sudo /usr/bin/python3 -I installers/radio_admin_trial.py --apply-mtu-recovery
```

Full backup and verification still take several minutes. Stop after any error; do not rerun or power-cycle. A90 remains uninstalled until the owner executes this transaction and activation is verified. Use the A90 read-only verifier below only after successful completion.

After A89, the owner reported volume keys still fail, forgot/re-paired, and the battery widget lost its displayed charge. Read-only verification confirms exact A89 code/methods, retained A86 fallback, original1053-byte SDP override, native management Input90 at82%, and native keyboard Feature2 with the exact11-byte configuration. The configuration also succeeds with the actual driver's512-byte capacity and returns length11. However, FnFunctionUsageMap and the parser's KeyboardLanguage/StandardType/alt_handler_id fields remain absent. Re-pairing has not fixed initialization.

The initial A89 verifier queried Feature2 through the raw maintenance interface and timed out. It has been corrected to use the exact native182-byte keyboard interface/F1 bridge. A direct raw FF selector attempt was rejected by macOS with NotPrivileged; it was not retried. Normal diagnostic reads and the native management/keyboard getters succeed. No firmware changes or device reset were made during these checks.

One independent, confirmed fault remains: the radio's configured48-byte channel clamp drops its existing79-byte device-information reply. Management initialization asks for that reply before reading battery state. Keyboard and management requests share a daemon mutex, so the resulting timeout could interfere with initial configuration; that lifecycle explanation is a hypothesis, not established causality. A90 repairs the demonstrated packet drop without adding more responses or mappings.

## Exact change and bounds

A90 retains the exact892-byte A89 component, SDP, estimator and physically verified WP recovery prefix. Its application version becomes90. One9-byte initialization record writes uint16 value128 at2007D2 before the final startup callback. Its full one-boot DS is16112 bytes, SHA256 `a700e0c2386c2e617fc26fcf7938fc7f94af61e322ad790d954953b4494535d6`, ending7EF0 below protected A86 at8000.

The ceiling is shared by outgoing negotiation, HCI HostBufferSize and generic incoming reassembly. HID's immutable advertised receive template stays48; pool sizes/counts stay unchanged. Actual ROM allocation uses size-aware buffers;99/140/148-byte requests fit the existing284-byte pool. Four such buffers are finite, so stress behavior and physical transmission remain unvalidated. This is not a claim that every possible traffic mix is proven safe.

Five MTU tests cover negotiation, unchanged local receive template, drop boundary, pool capacity and actual scatter/DS loading. Three full startup tests and three full HIDP tests pass; the latter reproduce the79-byte drop at48 and successful exact transmission to the modeled final queue at128. Six transaction tests, three runtime/negotiation verifier tests and seven administrator-helper tests pass. Completed-byte cut model checks16113 cut points; electrical torn writes remain outside the model. Astra independently recommended the bounded cap repair after reviewing its shared consumers and five MTU tests.

## Fresh baseline and update

The read-only full A89 backup after the owner's new pairing has SHA256 `b0824a4b3c6195c9e510bcf8fa9fb3bfa057d6171c5977cfcb112058549574e5`. Exactly17 changed bytes outside VS lie inside the first saved pairing slot, with two stable rereads of each affected16-byte chunk. All application code and headers match the expected installed A89 state. The baseline is retained privately; its link keys are never printed.

The installer pins that reviewed baseline and exact A89 runtime. It creates another fresh full backup before strict comparison or enabling updates, stages only DS4000, and commits SS0 byte0 last. A86, SS100, original code, settings and pairing are never written. It refuses unexpected new drift. The isolated dependency loader passes without opening a device or enabling firmware updates.

Owner-operated one-boot trial, only when ready to install; Bluetooth selected, USB power connected:

```sh
sudo /usr/bin/python3 -I installers/radio_admin_trial.py --apply-mtu-trial
```

Stop after any error. Keep power on after success. The read-only check is:

```sh
/usr/bin/python3 installers/verify_radio_mtu_trial.py
```

Physical acceptance requires exact A90 activation, ceiling128, negotiated outgoing limit79..128 and local receive48; successful native Feature34 with the correct address; keyboard configuration and Input90 replies; actual widget display, plain/Fn volume behavior and normal typing. Widget/volume improvement, Bluetooth-row display, runtime gain and calibration remain unproved. Another full power cycle falls back to A86.
