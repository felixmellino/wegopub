# Security and photo data handling

## Access to photos

Every photo page and check-in submission requires the account login helper.
It checks the current credential version, including after an administrator password change.
The server looks up the viewer's current lobby membership before each photo
download. The photo path must match the entry and lobby being opened.
It also checks the uploader's current account-wide sharing preference and
the current team roster under R6/R-PH01. Sharing defaults OFF, including
existing accounts. Owners retain access; current teammates can view their
saved team's photos internally. Opponents need the uploader and all current
members of that team to opt in. Missing consent denies sharing, and lookup
failures never authorize a download. Listing and direct downloads use the
same rule without caching consent. Chug Duel copies follow each owner's
setting independently, so the shared image can remain visible via the other
participant. Turning sharing OFF cannot recall bytes already delivered.
The photo view displays the username, team where applicable, capture time
and territory label, with an identity-coloured frame.

Apply `migrations/013_checkin_photo_privacy.sql` before deploying these
checks. The preference table permits only the server service role; profile
reads/writes validate the current account credential version. Preferences
are database-backed and apply to past and future photos across all lobbies.

Migration 013 was applied to the shared WeGoPub Supabase project on
19 November 2026 through its SQL editor. Eight checks passed: RLS enabled;
non-null boolean default false; primary key and cascading player link; no
PUBLIC grants; anon/authenticated denied; service-role read/write grants;
no opt-in records for existing accounts; and unchanged game record counts.
A fresh app-server process also read the empty table successfully via the
existing Supabase configuration. Deployed UI verification remains pending.

Storage uses the private `check-in-photos` bucket. The setup migration blocks
direct access by anonymous and authenticated Supabase clients and protects
the membership, season and drink-entry tables used for access decisions.
The app's service-role key stays on the server. Images are sent within the
authorized page, without a public storage URL.

For existing projects, `migrations/004_server_game_tables.sql` also protects
lobby invite codes, territory definitions, arenas and minigame attempts.
Public clients cannot bypass the app to read invites or change game state.
Fresh databases get the same restrictions from `schema.sql`. The account
migrations protect credentials, remembered sessions and reset codes. Password
recovery uses the existing server-only reset RPCs: hashed random 64-bit codes,
15-minute expiry, atomic single-use consumption, a one-minute issuance cooldown,
and the persisted login throttle shared by request/reset operations. Email is sent
through Brevo's HTTPS API using a server-only restricted key. The app sends HTML
and plain text without embedding remote images. Provider errors and recipient
information are not shown to players. Request response wording is identical for
unknown accounts, throttling and delivery failures; this does not guarantee equal
network timing. Changing a password invalidates active and remembered sign-ins
through the existing credential-version checks. Recovery never changes game data.

## Image handling

Check-in accepts camera JPEGs up to 10 MiB and 20 million pixels. The byte
limit and image dimensions are checked before the pixels are decoded. The
image is re-encoded with its orientation preserved and embedded metadata
removed. Photo GPS is not used for the location check (R-L01); the phone's
browser location and its reported accuracy are checked instead. Saved entries keep the
verification result and territory, and have empty exact-coordinate fields.
The photo setup migration clears exact coordinates from legacy entries too,
preserving scores and territory assignments.

Each capture has one entry ID and storage path. Retrying a submission uses
that ID and cannot insert another scored row. A failed upload records no
points. If an upload succeeds and a database save fails, retrying can finish
the same submission. An abandoned upload may leave a private unlinked file
until the retention process handles it.

## Configuration

Use HTTPS for the deployed app and the hosted Supabase endpoint. The app
rejects HTTP Supabase endpoints except on localhost. Streamlit's CORS and
XSRF protections are enabled. Usage telemetry is disabled in the project
configuration. Configure HTTPS and access to logs and backups with the
hosting provider.

Put local credentials in the ignored `.streamlit/secrets.toml`. Use the
hosting provider's secrets settings for deployment. Store service keys and
remembered-device tokens outside Git and issue descriptions.
If a secret is disclosed, revoke or rotate it at its provider, replace it
in the deployment secrets, and check access logs for misuse.
Use an encrypted secrets transfer rather than pasting keys into chats.
Coordinate replacement across the team's local apps and the deployment.
The current Supabase 2.9.1 client validates keys as JWTs. If replacing the
legacy service-role key with an `sb_secret_` key, upgrade and test the SDK
before the cutover. Follow the provider's
[key rotation procedure](https://supabase.com/docs/guides/security/rotate-leaked-api-keys)
so the exposed credential actually stops working.

## Dependency review

The security review on 17 November 2026 found advisories affecting the old
Streamlit, Pillow and pytest pins. Their replacements require Python 3.11
or newer. Run the full test suite after installing `requirements.txt` and
check the resolved packages with `pip-audit` before deployment.
The updated environment audit checked 70 installed packages and reported no
known advisories. This is a dated check; repeat it before deployment and after
dependency changes.

## Team decisions and deployment verification

R7 resolves the photo lifecycle part of D-13. The signed-in owner can delete
their image in Lobby photos. Ownership is checked on the server. The image
is removed and its reference is marked `deleted`; the entry and score stay.
Removal can be retried safely if a response is lost. Other members cannot
delete it. Copies already saved by viewers cannot be recalled.

Lobby access stops exactly 30 days after the season ends, using UTC.
Legacy season timestamps without a timezone are interpreted as UTC for this
cutoff. Cleanup removes expired objects and marks their reference `expired`.
Abandoned uploads without an entry have a 24-hour retry grace period since
their last update, then become eligible for removal. No scores are changed.

Run `python -m data.cleanup_checkin_photos` first to count eligible files.
Run `python -m data.cleanup_checkin_photos --apply` to remove them. The Data
owner must configure a server scheduler, at least daily, and monitor failures.
The command uses the same server secrets as the app. It reports counts only.
Run it from the repository root with the project's Python environment.
Expiry denies access immediately; physical removal occurs on the next
successful cleanup run. This repository does not provision a hosted scheduler.
Confirm the removal timing and any backup retention before collecting real
photos; do not promise immediate erasure of backups.

Before collecting real player photos, publish a privacy notice explaining
the purpose of the data, who runs the app, the lobby audience, retention,
the hosting providers and how to request access, correction or deletion.
Record the applicable basis for processing and the team's contact for
privacy requests. Confirm the project region and backup handling with the
Data owner.

Assign a team member to handle privacy and security reports. Verify the
requester's identity privately before exporting or deleting their records;
never post records or credentials in issues or the group chat. Requests from
former lobby members need that contact route. The team must define retention
for accounts and scored entries separately from the photo policy. For an
incident, restrict access, rotate affected secrets, preserve relevant logs
with limited access, establish which records were exposed, and assess any
notification duties using the team's applicable policy. Avoid logging photo
contents, exact GPS, passwords or access tokens.

Local verification on 17 November 2026: `python -m pytest -q` passed 155
tests, including photo deletion through the Streamlit page and retry after
partial failure. Temporary PGlite PostgreSQL checks exercised fresh and
upgraded schemas, repeat migration runs, preserved scores, GPS removal,
server access and public-client denial. The source scan found no matches
for common private-key, GitHub-token or Supabase-secret patterns. These
checks do not replace the configured project's live verification below.

Read-only connection checks on 17 November 2026 reached the shared project
and confirmed the core tables and account email column. The drink-entry
`photo_captured_at` column was missing (PostgreSQL code 42703), and the
`check-in-photos` bucket could not be retrieved. No shared records or schema
were changed.

The Data owner applied `migrations/004_server_game_tables.sql` and
`migrations/setup_checkin_photo_storage.sql` on 18 November 2026 and
verified, independently and against the live project (not just a
successful service-role request): the `photo_captured_at` column exists,
the `check-in-photos` bucket exists and is private, and an anonymous
Supabase client is denied (a real permission error, not just an empty
result) on both `territories` and `players`. No records existed to lose;
the shared project held 12 territories and zero players, lobbies, or
drink entries throughout.

A separate blocker was found: the installed `supabase==2.9.1` /
`storage3==0.8.2` client cannot parse the live Storage API's bucket
response (`SyncBucket.__init__() got an unexpected keyword argument
'versioning_status'`), which blocked photo upload, download, and cleanup
through the app. Unrelated to the migrations above.

The Data owner installed Python 3.11.18 (via pyenv) and validated
`supabase==2.34.1` in an isolated environment on 18 November 2026: the
app's own `_private_photo_bucket()` succeeds against the live project,
and the full suite passes (258/258) on Python 3.11 with this version.
`requirements.txt` is updated on a separate branch, not yet merged -- the
whole team needs Python 3.11+ installed before this lands, and the
rollout should be coordinated with whoever owns this security review.

The live check should include a successful upload and reopen after an app
restart, an outsider being denied, removal of a viewer's membership, and
direct object access through an anonymous Supabase client being denied.
Also verify owner deletion leaves scores unchanged, another member cannot
delete the image, expiry blocks downloads at the boundary, and two cleanup
runs remove expired and abandoned files safely without removing active ones.

Follow-up verification on 18 November 2026: the SDK upgrade was combined
with current main; 305 tests passed on Python 3.12.14. Real shared-project
storage checks with synthetic QA fixtures passed, including fresh-process
reopen, member/outsider/revoked-member access, owner deletion preserving
scores, and scoped expiry/cleanup. All QA fixtures were removed. The isolated
dependency audit is clean after updating pip to 26.3. See
[the verification record](STORAGE_SDK_VERIFICATION.md) for scope and limits.
The selected daily GitHub Actions workflow is prepared; private Actions
secrets, first hosted execution and monitoring still need setup after merge.

The upload controls follow the [OWASP file upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
The retention and notice work supports the [European Commission's data protection principles](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en).

## Profile pictures

`migrations/008_profile_pictures.sql` adds a separate server-only reference
table and private `profile-pictures` bucket. It does not alter Player or game
records. Apply it to new projects too, after account setup. The migration
refuses an existing public bucket and blocks anonymous/authenticated direct
object access. The app checks the viewer's credential version and current
accepted/pending relationship before retrieving another player's image.
Profile pictures are served as authorized inline bytes, without public or
signed object URLs. They are not cached across app requests. A cancelled,
declined or removed relationship loses access on its next request, although
already-displayed/downloaded copies remain outside our control.

Images are limited to 10 MiB/20 megapixels, decoded only as JPEG, PNG or WebP,
rotated using orientation metadata, centre-cropped to 512 by 512 and saved as
new JPEG pixels without metadata. Still pictures only; transparency is placed
on white. The owner alone may replace/remove their picture. Profile editing
and picture editing are separate saves; no new game points are generated.

A successfully replaced image is deleted where possible. Uncertain saves or
failed old-object deletion can leave private unlinked files. Configure daily
`python -m data.cleanup_profile_pictures --apply` alongside check-in cleanup;
without `--apply` it only reports. It keeps every current referenced picture
and gives abandoned uploads 24 hours before removal. Saved current pictures
remain until replaced/removed. Provider backups follow the team's separately
confirmed backup policy. Include this purpose, friend/request audience and
retention in the privacy notice before collecting real photos.

Live verification still required after the Data owner applies migration 008:
upload from a library and a phone camera; restart Streamlit and reopen on
another device; replace/remove; check owner, accepted friend, both directions
of a pending request and unrelated accounts; cancel/decline/remove and verify
further access ends. Confirm public-client table/object requests fail. Run
cleanup in dry-run mode and verify it never selects a current picture.

## Focus Challenge — 19 November 2026

Migration 014 keeps attempts/private random challenges server-only. Its game
RPCs use the trusted server role and also validate current player membership,
phase/revision, evidence shape, server deadlines, one-win limits and atomic
reward issuance under the existing lobby transaction lock. New-season snapshots
enable the feature; existing snapshots are unchanged. Source grants on entries
are immutable, so correction/replay cannot reapply an expired reward or compound
it. Exact eighth-point income is retained. No new package, credential, public
RPC access, photo, exact GPS or health classification is introduced.

Browser timing/tap evidence remains trust-based and can be manipulated by a
modified client. This is not a verified human/anti-cheat or sobriety assessment.
See [the implementation record](FOCUS_CHALLENGE.md) for tested access controls,
private challenge generation, restart recovery and outstanding activation checks.
