# Static regional distribution repository template

This is an inactive template, not a deployment or authorization to publish.
After approval, copy `publish.yml` to `.github/workflows/publish.yml` in a separate
public data-distribution repository. Copy the standalone
`src/sugarglider/offline_regions/unpack_distribution.py` to its root alongside
this README. Commit those source files only. Generated regional data belongs in
an explicit Release asset and the resulting Pages artifact, never Git history.

Enable GitHub Pages with the GitHub Actions publishing source. Create an explicit
release containing `sugarglider-regions-static.zip`, prepared and reviewed with
the main application's PR42 distribution tool. Dispatch Publish approved offline
region files with that release tag and the exact reviewed archive SHA-256.
No push, release creation or schedule starts the workflow automatically.

The workflow verifies the expected whole-archive hash, permits only regular,
strictly named static files, rejects traversal/symlinks/duplicates/compression,
and caps the site below GitHub Pages' published size limit. Deployment depends on
successful preparation. Only deployment receives Pages write and OIDC authority;
release downloading receives read-only repository authority. No routing server,
API, credentials, participant data or runtime application is hosted here.

Before enabling the app's download URL, verify the deployed HTTPS directory,
CORS, no redirects, untransformed compressed files, every size/hash and a real
Fairphone download. A green workflow is not proof of this client acceptance.

Pages deployment replaces the complete site. Prepare an update with
`--retain-directory` for the previous version. Never overwrite immutable files
or silently retire a currently supported version. This initial tool supports one
advertised region and one retained version. More retained versions/regions or
traffic beyond Pages limits require a separate hosting/retention decision.

See the main repository's `docs/pr42-static-distribution.md` for preparation,
current limits, licensing, approval gates and the publication checklist.
