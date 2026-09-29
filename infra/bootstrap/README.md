# Bootstrap

One-time setup for the platform, **applied locally by a person** (D-004). CI can't create the identities it authenticates with, so this root is never run by CI.

## What it manages

- **The `huaben` folder.** The three projects are imported and moved into it. A folder policy (`gcp.resourceLocations = in:eu-locations`) keeps resources in the EU.
- **Group access:** the admin group's organization roles, Owner on the folder for `gcp-platform-admins@`, and Billing Account Administrator for `gcp-billing-admins@`.
- **Essential Contacts:** `gcp-notifications@huaben.app`, for all notification categories.
- **APIs:** the ones the admin project needs, and the minimal set each environment project needs to enable its own.
- **The state bucket** `huaben-tracking-platform-tfstate` (EU, versioned, public access prevented). It holds this root's state under `bootstrap/` and each environment's under `envs/<env>/`.
- **CI identities:** Workload Identity Federation for GitHub Actions, and two service accounts per environment:

  | Account | Project roles | State access | Who can use it |
  |---|---|---|---|
  | `tf-plan-<env>` | Viewer, Security Reviewer | read `envs/<env>/` | any workflow run in this repository |
  | `tf-apply-<env>` | Viewer, Service Usage Admin, Project IAM Admin, Service Account Admin and User | read and write `envs/<env>/` | only jobs in the `<env>` GitHub Environment |

  - Tokens are accepted only from this repository, checked by numeric repository and owner ID.
  - The apply roles grow as later tickets add resources.

## Prerequisites

1. **Organization roles for `gcp-organization-admins@huaben.app`.** The admin grants these once, by hand; this root then records them. The roles are Folder Admin, Organization Policy Administrator, and Essential Contacts Admin:

   ```bash
   for role in roles/resourcemanager.folderAdmin roles/orgpolicy.policyAdmin roles/essentialcontacts.admin; do gcloud organizations add-iam-policy-binding "$ORG_ID" --member="group:gcp-organization-admins@huaben.app" --role="$role" --condition=None --quiet >/dev/null && echo "granted $role"; done
   ```

2. **APIs on the admin project.** Terraform bills its API calls to this project, so they must be on before the first run:

   ```bash
   gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com cloudbilling.googleapis.com billingbudgets.googleapis.com orgpolicy.googleapis.com essentialcontacts.googleapis.com iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com storage.googleapis.com --project=huaben-tracking-platform-admin
   ```

3. **Variables.** Copy `terraform.tfvars.example` to `terraform.tfvars` (gitignored) and fill in the organization and billing account IDs.

4. **Logins.** You're logged in with `gcloud auth application-default login` as a member of `gcp-organization-admins@`, `gcp-platform-admins@`, and `gcp-billing-admins@`.

## First run

The state bucket doesn't exist until the first apply, so the first run uses local state and then moves it into the bucket.

```bash
mv backend.tf backend.tf.off
terraform init
terraform plan -out=bootstrap.tfplan
terraform apply bootstrap.tfplan
mv backend.tf.off backend.tf
terraform init -migrate-state
rm terraform.tfstate terraform.tfstate.backup bootstrap.tfplan
```

- **Review the plan before applying.** Existing projects should only be imported and moved into the folder (`org_id` → `folder_id`), with nothing destroyed.
- **`terraform init -migrate-state`** asks to copy the local state into the bucket. Answer `yes`.
- **Delete the local state files** only once the migration has succeeded.

Then create the environments' empty state files, once:

```bash
(cd ../envs/dev && terraform init) && (cd ../envs/prod && terraform init)
```

This is needed because the CI plan accounts are read-only (D-013). When `terraform init` finds no state, it tries to create it, and the plan accounts' write is refused, so PR plans fail until the state files exist. After that, plans only read the state.

After the first run, the project-level Owner grants for `gcp-platform-admins@` are redundant, because the folder grant covers them. You can remove them by hand.

## Later runs

```bash
terraform init
terraform plan -out=bootstrap.tfplan
terraform apply bootstrap.tfplan
```
