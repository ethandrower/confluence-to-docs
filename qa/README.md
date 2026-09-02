# QA for the support portal

Two layers, doing different jobs.

**`python manage.py smoke --url <deployment>`** is the automated one. It walks
nine checks against a *running* server over real HTTP — health, the SPA shell,
every static asset the shell references, anonymous-access refusal, magic-link
sign-in, session identity, the file tree including tenancy, tickets, sign-out.
CI runs it against a production-parity stack on every PR. It is the thing that
catches a release-phase failure the 661 Django tests structurally cannot see,
because those use the in-process test client and so never build a bundle,
resolve a static asset, terminate TLS, or read the container's environment.

**`qa/qase/support-portal-cases.yaml`** is the manual one: 60 cases covering
what a person has to look at — the shape of the upload UI, what a customer
actually receives, whether a dead end explains itself. Every case in it was
walked by hand against a real deployment before it was written down.

The two do not overlap by accident. Anything the smoke test can assert belongs
in the smoke test; the YAML is for judgement calls.

## Pushing the cases to Qase

```bash
export QASE_TESTOPS_API_TOKEN=...        # app.qase.io → user menu → API tokens
pip install pyyaml                       # requests is already in requirements.txt

python qa/qase/push_to_qase.py --dry-run # see what would change
python qa/qase/push_to_qase.py           # create/update
```

It is idempotent — project matched by code, suites by title, cases by title
within their suite — so editing the YAML and re-running is the intended
workflow. **The YAML is the source of truth and Qase is a projection of it.**
Edit cases here and push; do not edit them in the Qase UI, or the next push
will overwrite the change.

The project code is `CSP`. Change it in the YAML if that collides with an
existing project — `QAC` is the QA-challenge sandbox and is not this.

## Cases that record a defect rather than the desired behaviour

Seven cases are tagged `known-defect`. They describe what the portal does
*today*, deliberately, so that a green run is honest rather than quiet about a
gap. Each one names the desired behaviour in its expected result. Fix the
product, then fix the case — in that order.

| Case | What it pins down |
|---|---|
| Creating a customer sends them nothing | There is no invite email at all. `POST /api/admin/users/` writes the row and returns; the customer is never told the account exists. |
| Customer created with no company reaches a dead end | The company dropdown defaults to "— None —", and such a user can sign in but can do nothing. The reason only appears after they try. |
| A multi-file drop sends one email per file | Three files produced three staff emails. Twenty would produce twenty. |
| A failing mail provider is invisible to the user | Reproduced with an invalid Mailgun key: provider returned 401, portal reported success. Right for account enumeration, wrong as the only signal. |
| Raising a notice emails nobody | `SiteNotice` has no mail path at all — `_notify` only broadcasts over the WebSocket. Both the model docstring and `views/notices.py` say EC-SOP-07 §5.2 names email to the designated account contact and that the banner merely *supplements* it. The supplement is the half that exists. |
| The only notice channel is unreachable during the incident it describes | The banner shares fate with the portal — one host, one web container — so it cannot render during the SEV-1 it is meant to announce. With no email path, a total outage is exactly the case where customers can be told nothing. |
| The notices history page has no way in | The only link to `/notices` is inside the banner, on the first live notice. No nav entry exists, so with nothing live the page is reachable only by typing the URL — and dismissing the last notice removes the link too. |

## Test accounts

Use `+` addressing on one real inbox so every test account is reachable
without creating new mailboxes: `ethandrower+qa1@gmail.com` and so on. Staging
carries `qa1` and `qa2` against **Northwind Medical (QA)**, and `qa3`
deliberately against *no* company, which is what the dead-end case above
exercises.

`STAFF_EMAIL_DOMAINS` is `citemed.com` only, so a gmail address is always a
customer — which is what makes these safe for tenancy tests.

## Running a case by hand

Mint a link rather than waiting on mail:

```bash
# locally, against the parity stack
docker compose -f docker-compose.prod.yml run --rm --no-deps release \
    python manage.py magic_link --email ethandrower+qa1@gmail.com

# on staging
ssh root@157.90.131.248 \
    "dokku run citemed-docs-staging python manage.py magic_link --email ethandrower+qa1@gmail.com"
```

Staging sends mail to the application log (`EMAIL_BACKEND` is the console
backend and `MAILGUN_ACCESS_KEY` is empty), so the whole message — magic links
included — is readable with `dokku logs citemed-docs-staging`. That is what
makes the notification cases runnable there at all. **Setting a placeholder
Mailgun key instead would make sends fail against Mailgun rather than fall
back**, which is exactly the 401 the last known-defect case describes.
