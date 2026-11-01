# Third-party provenance

The Go2 environment code was adapted from the Genesis locomotion examples through the preserved local project. Genesis1.4.5 is distributed under Apache2.0; its installed license text is included in `LICENSES/Genesis-Apache-2.0.txt`. The complete original-to-integrated file hashes are listed in `manifests/code-port.json`. Changes include package paths, bounded terrain integration and separately versioned training/reset additions.

RSL-RL5.0.0 is used as an installed dependency; its source is not vendored. The installed distribution license is retained in `LICENSES/RSL-RL-license.txt`. Dependency versions are recorded in `requirements-macos-arm64.lock.txt`.

Unitree Go2 URDF/meshes are read from the existing Genesis installation and are not redistributed here. Their original asset notices remain in that installation. Model weights, private experiment media and other third-party assets are not part of this Git change. The approved rolling heightfield is project-generated reference data.
