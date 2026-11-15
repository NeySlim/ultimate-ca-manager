# Software bill of materials (SBOM)

Every release ships one CycloneDX 1.6 JSON document per deliverable: one per package file (the DEB and the three RPMs) and one per image platform (standard and FIPS, amd64 and arm64). The release workflow refuses to tag an image or create the release if one of them is missing, empty, invalid against the CycloneDX 1.6 schema, made for another version, or describing another file or image.

## Where to find them

On the GitHub release page of each version, next to the packages:

| Deliverable | SBOM asset |
|---|---|
| `ucm_<version>_all.deb` | `ucm_<version>_all.deb.cdx.json` |
| `ucm-<version>-1.fc43.noarch.rpm` (and the `el9`, `el10` RPMs) | `<package file name>.cdx.json` |
| Image `<version>`, amd64 or arm64 | `ucm-<version>-image-standard-<arch>.cdx.json` |
| Image `<version>-fips`, amd64 or arm64 | `ucm-<version>-image-fips-<arch>.cdx.json` |

`<version>` is written as in the asset names, with dots: `3.0.rc1` for the release candidate `3.0-rc1`. Each SBOM has its `.sha256` file, and `sbom-index.json` (with its `.sha256`) lists every deliverable with its SBOM and both checksums.

## Matching an SBOM to what you downloaded

- **Package**: `metadata.component.hashes` holds the SHA-256 of the package file and the property `ucm:asset` its name. Compare with `sha256sum <package>`.
- **Image**: `metadata.component.hashes` and the property `ucm:image-digest` hold the digest the build pushed for that platform, the one the release tagged, and `ucm:arch` and `ucm:variant` its architecture and variant. `docker pull <image>@<digest>` fetches exactly that image; a tag can be moved, a digest cannot.

The checksum files tell whether a file is the one the release published; they do not sign it.

## What each document says

Each component carries a role in the property `ucm:role`:

- `content`: shipped in the deliverable. For the images: the operating system packages (read by Trivy from the package database), the Python distributions with the version and licence their installed metadata declare, libraries bundled inside wheels (by file and hash, version unknown), the OpenSSL FIPS Provider of the FIPS image (version and source archive from the Dockerfile, hash of the binary actually copied), the Python version the base image declares. For every deliverable: UCM itself, the legal texts, the npm packages whose code the bundler put into the web interface (with the bundle files that carry them) and the fonts, with their licence.
- `build-input`: npm production dependencies used by the build whose code is not in the bundle.
- `install-requirement`: what a package needs on the host. Python requirements keep their constraint as written (`SQLAlchemy>=2.0.45,<2.2`, never a version), with `--no-deps` for pyjks and the substitutions of a `UCM_FIPS_BUILD=1` install; system dependencies keep their `Depends`/`Requires` line.

A licence the evidence does not give is left out and the component carries `ucm:license` = `unknown`: no component receives UCM's licence by default.

## What they do not cover

- **The host**: its system, kernel, container runtime, volumes and external services (database, Redis, identity providers).
- **Dependencies resolved at installation**: the DEB and RPM packages hold no Python environment; pip resolves the requirements on the host, so the versions installed there depend on the host and the date. An installed system is described by inspecting it, not by the package SBOM.
- **Anything added after installation**: packages an administrator installs (an HSM library, Kerberos extras), changed files, a modified image.
- Code statically linked into native extensions that no package metadata declares, and npm build tools (development dependencies).

The SBOM is an inventory, not a vulnerability report, and it makes no FIPS certification claim for an image as a whole.
