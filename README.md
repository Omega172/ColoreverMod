# Mod for Colorever

[Colorever](https://apps.apple.com/us/app/colorever-gem-art-puzzle/id6761757565) 1.23.0 mod for arm64 iOS.

## Features

- Ad blocker
- Infinite Powerups - hint, shuffle and temporary expansion show 999 without consuming inventory. Normal unlocks still apply.
- Signing compatibility - handlers for the protection checks, poison writes and self-termination paths, including the file-save freeze fix.
- Settings message beneath the game version: "I bypassed your fuck-ass VM-based protection ~ Omega172".

## Beating the bullshit VM-based code virtualization

Hey Tencent, I bypassed your shit,

Re-signing even the unmodded app caused random-ass crashes. `anortx.framework` hides protection code in a custom VM and fights back with heap poisoning, SIGKILL and bogus zero-byte file writes that freeze level saves. Team ID spoofing, `ldid` and patching the obvious native path didn't fix shit.

Live debugging caught the actual VM writes, self-kill calls and blocked saves. My C++ handlers skip the poison store, bypass the native poison and kill helpers and return success from the native validator so real file writes complete. Version-checked ARM64 bridges connect those handlers to the game. The VM still runs; its confirmed destructive paths get told to fuck off.

The fingerprints strongly point to Tencent Anti-Cheat Expert (ACE) iOS hardening and its proprietary **ObjVM**: the framework identifies itself as `ace.anort` and contains `anort::ObjVMHeartBeatProtect` and `anort::ShellFuseProtector`. [ACE's engineering article](https://intl.anticheatexpert.com/resource-center/content-84.html) describes ObjVM and Mach-O static merging. Its [iOS product page](https://intl.anticheatexpert.com/products/code-encryption-ios/) also lists virtualized verification, metadata encryption and repackaging detection. The exact SDK revision remains unidentified.

## Build

Edit `Project.json` to set the mod project name, SDK, minimum iOS target and C++ dialect. These settings only affect the mod and its outputs. The app identifiers, name and version are preserved.

Install Theos and its iOS compiler and SDK in Linux. Set `THEOS` to that installation, or use the default `$HOME/theos`. The project path must not contain spaces.

On Windows, run `Build.bat`. It invokes plain `wsl`, using your default distribution and user.

On Linux, run `bash ./Build.sh` from the project folder. Both scripts compile the dylib to `Build/Release/ColoreverMod.dylib`.

Gameplay and protection logic lives in `Source/Mod/RuntimeHooks.mm`. The packager verifies the original framework hashes and instructions, then installs signed ARM64 bridges that call the exported C++ handlers. Handler addresses are cached in verified writable padding. Ad hooks use the Objective-C runtime, as in CubeAwayMod.

### Package a provided IPA

Use the supported decrypted Colorever 1.23.0 IPA. From the project folder:

```powershell
.\Package.bat "./Game.ipa"
```

```bash
bash ./Package.sh "./Game.ipa"
```

Python 3.11+ is required for packaging. The commands build the dylib and produce `Build/Release/ColoreverMod-NeedsSigning.ipa`. You can omit the input path if the project root contains exactly one IPA, or pass a direct HTTPS IPA URL instead. Existing output is replaced only after verification succeeds.

Gameplay and protection handlers require the packaged IPA's signed bridges. Sign the complete IPA before installing it. The C++ runtime-handler build still needs on-device testing.

### Build with GitHub Actions

Open the repository's **Actions** tab and select a workflow:

- **Build and Draft IPA Release**: click **Run workflow**, enter a new `version` tag and a direct HTTPS `ipa_url`. The draft release includes the modded IPA and dylib.
- **Build and Draft Dylib Release**: click **Run workflow** and enter a new `version` tag. The draft includes only the dylib and needs no IPA.

Find the output under **Releases**.
