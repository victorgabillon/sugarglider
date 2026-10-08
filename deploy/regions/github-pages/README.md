# Static regional distribution repository template

This is an inactive template, not a deployment or authorization to publish.
After approval, copy `publish.yml` to `.github/workflows/publish.yml` in a separate
public data-distribution repository. Copy the standalone
`src/sugarglider/offline_regions/unpack_distribution.py` to its root alongside
this README. Also copy `src/sugarglider/offline_regions/copy_public_privacy.py` to
the root and this directory's `privacy/index.html` to `privacy/index.html`.
Work must fill the privacy template's public publisher/contact, effective date,
hosts and operator settings, review the policy against the actual deployment,
and change `data-policy-status="draft"` to `"approved"`. The workflow rejects
unfilled placeholders or an unapproved page. It copies the reviewed HTML bytes
after verified extraction; it never changes the regional ZIP or its files.
Commit those source files only. Generated regional data belongs in
an explicit Release asset and the resulting Pages artifact, never Git history.

Enable GitHub Pages with the GitHub Actions publishing source. Create an explicit
release containing `sugarglider-regions-static.zip`, prepared and reviewed with
the main application's PR42 distribution tool. Dispatch Publish approved offline
region files with that release tag and the exact reviewed archive SHA-256.
No push, release creation or schedule starts the workflow automatically.

The Release asset is the complete prepared ZIP. **Pages serves the complete
extracted regional directory, including the large map and routing archives**,
alongside catalog, attribution and `/privacy/`. Individual Release-asset URLs are
not substituted into the app: they do not provide the unchanged relative layout
and can redirect. A host that cannot serve these exact paths and bytes does not
satisfy the prepared client contract. Work must report that incompatibility.

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
one `--retain-directory` per still-supported previous version. The tool supports
one advertised region plus zero or more retained immutable versions of that same
region, bounded by the complete publication's size and archive-safety limits.
Every version is verified independently and copied byte-for-byte. Only the current
build appears in the catalog; retained build IDs are sorted deterministically.
Never overwrite immutable files or silently retire a supported version: every
version that must remain addressable must be included in the replacement site.
Another geographical region or traffic beyond Pages limits requires a separate
hosting decision.

For example, retain two versions with:

```sh
uv run python -m sugarglider.offline_regions.distribution \
  --region-directory /data/new \
  --retain-directory /data/current-old \
  --retain-directory /data/older \
  --output-directory /data/new-publication \
  --base-url https://victorgabillon.github.io/sugarglider-regions/ \
  --description 'Reviewed regional coverage description'
```

Preparation is local only. The 950,000,000-byte budget includes every regional
version plus reserved overhead, and available disk space must cover the site and
ZIP. The existing 128-member archive metadata bound is also checked before
assembly; with the fixed seven-file regional layout it permits up to 17 complete
versions. This is an archive-safety bound, not a two-retained-version special case.

The standalone unpack verifier must be copied from the reviewed application
revision before a later publication. It verifies the catalog's one current row
against the advertised manifest and checks every retained manifest's region/build
path identity before extraction. The workflow, manual dispatch, archive-hash gate,
privacy gate, pinned actions and deployment permissions remain unchanged.

See the main repository's `docs/pr42-static-distribution.md` for preparation,
current limits, licensing, approval gates and the publication checklist.

The integration candidate's `docs/work-publication-handoff.md` contains the exact
verified artifact inventory, URLs, source revisions and Work return contract.
`yvelines-publication.json` is publication verification metadata, not generated
map/index content. Public deployment and Play operations belong to Work; the
integration branch and original draft PRs remain unmerged to main by Codex.
