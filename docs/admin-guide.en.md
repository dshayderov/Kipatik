# Kipatik Administrator Guide

This document describes everything a platform administrator can do: get access to the panel, manage users, roles, and projects, enable and unload code analysis models, configure storage limits, deploy the system, and troubleshoot its failures.

Who this guide is for: a system administrator responsible for deploying and operating Kipatik, and a project administrator tasked with managing accounts and settings.

How the two guides relate:

- **The User Guide** covers day-to-day work in the system: the board, tasks, comments, connecting a repository, project invitations.
- **The Administrator Guide** (this document) covers everything outside the user's workspace: accounts, roles and permissions, models, storage, deployment, and diagnostics.

The boundary is the “superuser” flag: only a superuser sees the admin panel. Everything inside a project is described in the User Guide.

> **Caution: the default password.** On the first server startup an account
> `admin@example.com` with the password `admin` and administrator rights is
> created. Change the password immediately after the first login. Details — in section 9.3.

---

## 1. Obtaining administrator rights

Administrator rights are the “superuser” flag on an account. It is not granted during registration and is not configured in the profile: by default a new user does not have it, so only someone who already has it can grant the rights.

Ways to get access:

1. **Log in with the account created on the first server startup** (`admin@example.com` / `admin`) — the only method that works on an empty system.
2. **Get the flag from another administrator**: they open «Управление пользователями» (“User management”) and click the shield icon in the «Админ» (“Admin”) column next to your account.

What happens after the rights are granted: on login the admin panel opens immediately, not the workspace; all five sections are available; the data of all users, projects, and roles is visible without restrictions; projects in which you are not a participant open automatically with the rights of a project leader.

Permission checks work on two levels: in the interface the admin panel is not shown to a regular user and an attempt to open it returns to the home page; on the server every request to an administrative section checks the superuser flag, and without it the server responds with a 403 rejection.

You cannot remove the rights from your own account: the server rejects such a request, and the interface does not allow it to be performed. This protects against accidentally losing the only administrator.

A blocked user loses access to all sections, including the administrative one: the block is checked on every request, a valid login token does not help.

---

## 2. The admin panel

The panel is available at `/admin` and consists of five tiles:

| Tile | Section | Contents |
|---|---|---|
| «Управление пользователями» (“User management”) | `/admin/users` | Accounts, blocking, admin rights, the permission to create projects |
| «Управление ролями» (“Role management”) | `/admin/roles` | Project roles and permission sets |
| «Управление проектами» (“Project management”) | `/admin/projects` | All projects, their participants, and roles |
| «Управление нейросетевыми моделями» (“Neural model management”) | `/admin/models` | Enabling, unloading, and warm-up of models |
| «Управление хранилищем» (“Storage management”) | `/admin/storage` | Attachment limits, trash, auto-cleanup |

At the bottom of the start screen there is an information block about the superuser's unlimited access. It is advisory in nature: any change made here affects the whole platform and all projects, including other people's. Breadcrumbs are shown in the page header — they let you return to the list of sections.

General rules for working with the panel:

- changes apply immediately and survive a restart unless stated otherwise;
- model and storage settings are stored in the database, not in the settings file;
- the set of data on the screen is refreshed every time a section is opened, so changes made by another administrator are visible without reloading the page.

---

## 3. Users

The «Управление пользователями» (“User management”) section is the list of all accounts. The add button is in the top right corner.

### 3.1 Table and search

The table shows: avatar, full name, email, status, administrator flag, “can create projects” flag, and actions. The search field above the table searches by name and email at the same time; it runs on the server, so it works on large volumes too.

Limit: the server returns at most 100 accounts per request, and the interface has no pagination. On a system with more than a hundred users, look for the person you need with the search — without it the list is not shown in full.

### 3.2 Creating a user

| Field | Purpose |
|---|---|
| Login / Email | Required. Used for signing in |
| Full name | Displayed in the interface and in lists |
| Password | Required on creation, with show and hide |
| «Админ» (“Admin”) | Superuser flag |
| «Создание проектов» (“Project creation”) | Permission to create projects |

The server rejects the creation of a user with an email that already exists. When changing the address of an existing user this check is not performed — set the new address carefully.

### 3.3 Editing a user

The pencil icon in the «Действия» (“Actions”) column opens the same window. When editing, the password field can be left empty — then the old password is kept. The «Админ» (“Admin”) and «Создание проектов» (“Project creation”) flags and the status are changed both here and with separate buttons in the table; the result is the same.

### 3.4 Blocking and unblocking

The toggle is in the «Статус» (“Status”) column: clicking the «Активен» (“Active”) badge switches the user to the «Заблокирован» (“Blocked”) state, clicking «Заблокирован» restores access.

Blocking is reversible and deletes nothing: access to the system is closed on the very next request (a valid token does not help), and projects, tasks, history, and administrator rights are kept and return together with access. Restoring it is the same toggle; for full deletion use the trash icon in the «Действия» (“Actions”) column.

### 3.5 Administrator rights

The shield icon in the «Админ» (“Admin”) column turns the superuser flag on and off; the action is disabled for your own account.

A practical note: inside any project a superuser has the rights of a project leader, even if they are not a member of that project. This is convenient for incident investigation, but it means the ability to change the contents of someone else's project. Agree on the rules inside the team before granting the rights.

### 3.6 The permission to create projects

The checkmark icon in the «Создание проектов» (“Project creation”) column manages the permission to create new projects. By default it is off for everyone who registered on their own; it is on only for the first-run account and for those you explicitly granted it to. Revoking the permission does not delete already created projects — it only forbids creating new ones.

### 3.7 Deleting a user

The trash icon in the «Действия» (“Actions”) column deletes the account after confirmation. You cannot delete yourself: the action is unavailable and the server rejects it.

| Item | Result on deletion |
|---|---|
| Account and participation in projects | Deleted |
| Projects the user owned | Remain in the system with no owner who could manage them |
| Tasks, comments, history | Stay in place |

Therefore deletion is not a replacement for blocking. If the user's data may still be needed, block the account; delete only those whose data is no longer needed.

---

## 4. Roles and access permissions

The system has two permission levels: **platform administrator** (section 1) and **project roles** (this section). A project role does not grant access to the admin panel.

### 4.1 System and custom roles

| Role type | What it is | Can it be deleted |
|---|---|---|
| System | Five base roles: Project Manager, Manager, Developer, Tester, Observer | No: the delete button is hidden, the server rejects the request |
| Custom | Any role you created in the panel | Yes |

The role card shows the name, the description, the number of assigned permissions, and — for system roles — the «Системная роль» (“System role”) badge.

Creating and editing a role: fill in the name, the description, and check the required permissions in the checkbox grid. Below the grid a counter of the selected permissions and a note that the permissions apply globally in all projects where the role is used are shown. There are no separate permissions at the level of an individual project.

### 4.2 List of permissions

The system defines 34 access permissions, of which 33 are granted from the panel:

| Group | Permission | What it allows |
|---|---|---|
| Project | `project:view` | Viewing a project |
| Project | `project:edit` | Changing project settings |
| Project | `project:delete` | Deleting a project |
| Project | `project:invite` | Inviting users |
| Project | `project:remove_member` | Removing a participant from a project |
| Project | `project:manage_roles` | Assigning roles to participants |
| Project | `project:connect_repo` | Connecting and configuring a repository |
| Project | `project:manage_columns` | Managing board columns |
| Project | `project:manage_labels` | Managing labels (no functionality) |
| Project | `project:view_settings` | Viewing project settings |
| Board | `board:view` | Viewing the board |
| Board | `board:manage_columns` | Creating and editing columns |
| Board | `board:move_task` | Moving cards between columns |
| Task | `task:view` | Viewing a task |
| Task | `task:create` | Creating a task |
| Task | `task:edit` | Editing a task |
| Task | `task:delete` | Deleting a task |
| Task | `task:assign_self` | Assigning yourself as assignee |
| Task | `task:assign_other` | Assigning an assignee to another participant |
| Task | `task:manage_priority` | Changing the priority |
| Task | `task:manage_deadline` | Changing the due date |
| Task | `task:manage_labels` | Task labels (no functionality) |
| Task | `task:manage_subtasks` | Working with subtasks |
| Task | `task:close_reopen` | Closing and reopening a task |
| Task | `task:git_link` | Linking commits, branches, and pull requests to a task |
| Task | `task:ai_approve` | Confirming model suggestions |
| Comments | `comment:create` | Writing comments |
| Comments | `comment:edit_own` | Editing your own comments |
| Comments | `comment:delete_any` | Deleting any comments |
| Code review | `pr:view` | Viewing merge requests |
| Code review | `pr:comment` | Commenting on a pull request |
| Code review | `pr:approve` | Approving a pull request |
| Code review | `pr:merge` | Merging a pull request |

The thirty-fourth permission — managing project rules — is missing from the panel list: it cannot be granted from the interface, and there is no function behind it in the system.

### 4.3 Default permission matrix

Permissions are applied from two sources, and it is important for an administrator to understand this:

1. if the database has a role record with that name — the **permission set from that record** is applied, that is, exactly what you checked in the panel;
2. if there is no record in the database — the **built-in matrix** for the role name is applied.

| Role | project | board | task | comment | pr |
|---|---|---|---|---|---|
| Project Manager | All 11 | All 3 | All 13 | All 3 | All 4 |
| Manager | 8: without project deletion and repository connection | All 3 | All 13 | All 3 | All 4 |
| Developer | Viewing, labels | Viewing and moving | Creating, viewing, editing, assignment, priority, due date, subtasks, closing, Git, confirming models | Creating and editing own | Viewing, commenting, approving, merging |
| Tester | Viewing | Viewing and moving | Creating, viewing, self-assignment, labels, subtasks, closing, Git, confirming models | Creating and editing own | Viewing, commenting, approving |
| Observer | Viewing | Viewing | Viewing | — | Viewing |

Practical consequences:

- **Editing a role through the panel fully replaces the matrix**, it does not supplement it: remove a permission and it is gone, even if it is in the matrix.
- **Deleting a role from the database returns the system to the matrix.** If you created a custom role, assigned it to participants, and then deleted the role, the participants stay in the project, but the permissions become the matrix ones — that is, most likely, missing ones, because the name of a custom role is not known in the matrix. Remove participants from a role you are going to delete beforehand.
- **The built-in matrix cannot be changed from the interface**: system roles have records in the database, and the matrix is not applied to them while the record exists. To change the behaviour of a system role, edit it through the panel like any other role.

### 4.4 Restrictions that apply on top of permissions

Part of the rules is not defined by permissions but by code, and they cannot be bypassed from the panel:

| Rule | Meaning |
|---|---|
| A developer and a tester edit only tasks assigned to them | Even with the permission to edit other people's tasks, the server rejects the change |
| A tester cannot assign tasks to other participants | The permission exists in the matrix, but the server restricts it |
| A developer can reassign only the task they are working on | The same restriction |
| A manager cannot assign the «Руководитель проекта» (“Project Manager”) role | Protection against a second leader appearing bypassing the owner |
| A manager cannot remove a participant with the «Руководитель проекта» (“Project Manager”) role | The same restriction on removal |
| Only the owner or an administrator can delete a project | The delete permission is not granted in roles |
| A superuser automatically gets the rights of a project leader | Even if they are not a participant of the project |

---

## 5. Projects (administration)

The «Управление проектами» (“Project management”) section shows all projects in the system, including those the administrator is not a member of. This is the main tool for incident investigation and centralized management of team composition.

### 5.1 List and search

The list shows the project name, its identifier, the description, and the owner (name and email). The search filters the list by name and description right in the browser, without a request to the server, so it works instantly. If there are no projects, the empty state «Проектов пока нет» (“No projects yet”) is shown.

### 5.2 Project participants

The «Участники» (“Participants”) button opens the composition of the project team. Four actions are available from the admin panel:

| Action | How to perform | Effect |
|---|---|---|
| Viewing the composition | Open «Участники» (“Participants”) | List: name, email, role |
| Adding a participant | «Добавить» (“Add”) → search by name or email → choose a role → «Добавить» (“Add”) | The participant appears in the project immediately |
| Changing a participant's role | Select the role next to the participant | The new role applies immediately |
| Removing a participant | The delete icon next to the participant | The participation record is removed |

Differences from the regular participants window available to the Project Manager:

- **no invitation and confirmation** — the participant is added immediately, there is no separate request to accept;
- **no project restrictions by role** — an administrator can assign the «Руководитель проекта» (“Project Manager”) role and remove a participant with that role, although in the regular window such actions are forbidden to a manager;
- **no check for participation in another project** — one person can be a participant of any number of projects;
- **removing a participant does not touch the data** — tasks, comments, commits, and history remain, only the participation record disappears.

If the selected role is not found in the database for some reason, the participant is recorded with the base role «Разработчик» (“Developer”). After the assignment it is worth checking in «Управление пользователями» (“User management”) that the person is active: a blocked participant will not be able to work in the project.

### 5.3 Project settings

The «Настройки» (“Settings”) button opens the regular project settings window — the same one the Project Manager sees: the Git connection tab, the project background, project deletion. The only difference is the permission check: an administrator has access to what is not available to a participant, including project deletion. The operation is irreversible.

### 5.4 Changing a role in the regular participants window

In the user-facing project participants window, changing a role with a dropdown does not work at the moment: the interface sends a request for which the server has no handler. Only the admin path from this section works. If users complain that a role “does not save”, make the changes here.

---

## 6. Neural models

The «Управление нейросетевыми моделями» (“Neural model management”) section is the only place where code analysis and work volume estimation models are enabled, unloaded, and warmed up.

### 6.1 Which models exist and what each one does

| Model | Kind | Purpose | Dependencies |
|---|---|---|---|
| Trace encoder | Neural network | Converts commit messages and task texts into vectors and uses them to pick a task for a commit. The heaviest part: about a gigabyte of weights, kept in memory permanently | — |
| Commit type classifier | Neural network | Determines the type of a commit from the meaning of the changes: fix, feature, refactoring, documentation, tests, other | Works on top of the encoder, cannot be enabled separately |
| Work volume estimation | Rules | Calculates task progress from the volume of changes, subtasks, and files named in the description. No neural network is used | — |

At the top of the page there are three metrics: the total volume of artifacts on disk, how many models are loaded in memory right now, and how many are enabled.

### 6.2 Artifacts and where they live

| Artifact | Default name | Size | What it is |
|---|---|---|---|
| Encoder weights | `commit_tracer.pt` | ≈ 1061 MB | The main weights of the matching model |
| Classifier weights | `type_classifier.pt` | ≈ 0.8 MB | Only the “head” of the classifier on top of the frozen encoder |
| Tokenizer folder | `paraphrase-multilingual-mpnet-base-v2` | ≈ 13.5 MB | Five files: architecture configuration, vocabulary, and its description |

Where to get the files: they are in the repository, in the `code_model` folder next to the code, that is `backend/app/ai/code_model`. Cloning gives a complete set — the weights of both models, the progress rules module, and the vocabulary folder. There is nothing to download or place by hand. The root is overridden by the `CODE_MODEL_DIR` variable, the weight file names by the `CODE_MODEL_TRACER_FILE` and `CODE_MODEL_CLASSIFIER_FILE` variables; the vocabulary folder name is fixed.

Critically important:

- **The weight files contain only the weights.** The model architecture and the vocabulary are taken from the tokenizer folder. Without it the model **will not start**: the panel will show the «файл не найден» (“file not found”) badge, and diagnostics will show the reason `tokenizer_missing`.
- **The vocabulary and the weights are in the repository.** Cloning gives a complete set. If the vocabulary is ever lost it can be restored on its own: `python backend/scripts/fetch_tokenizer.py`; a check without downloading is `python backend/scripts/fetch_tokenizer.py --check`.
- **The large weights are stored with Git LFS.** The encoder weighs about a gigabyte, and GitHub has a hard limit of 100 MB per file, so it cannot be pushed with plain git. Cloning a repository without LFS succeeds, but the files stay as small pointers and the model reports `tracer_missing`. Run `git lfs install` before cloning; check the state with `git lfs ls-files`.
- **`torch` is required, and it is not in the server dependency list.** It is installed with a separate command given in the dependency file itself: first `torch` from the CPU index, then `transformers` and `numpy`. Without it the Docker image will build and start, but it will not be able to work with models: the page will show that the artifacts are in place, and the load will end with an import error. Full `torch` pulls in a build with video support of about 2.5 GB — therefore the CPU variant is recommended. A separate build argument is provided for building the image, which adds `torch` to the image; without it the image runs without models, and that is a deliberate decision.
- The models take about 1.1 GB of disk space and about 1.6 GB of RAM when running on CPU. Check the free disk and memory before enabling them.

### 6.3 Enabling and disabling

The power button on the model card toggles its state. The decision is written to the database, takes effect immediately, requires no restart, and is preserved between restarts.

| What is important to understand | How it works |
|---|---|
| Two sources of state | Until your first decision the value from the settings file applies; after that — the decision from the database |
| The «изменено» (“modified”) badge | Your decision differs from the value in the settings file. This is a hint, not an error |
| Who and when | The author name and the modification time are stored and shown on the card |
| Dependencies | The classifier cannot be enabled while the encoder is disabled: the server rejects the request and suggests enabling the encoder first |
| Disabling ≠ unloading | Disabling stops the use of the model but does not free memory — unloading is required for that (section 6.4) |

Badges on the model card: «нейросеть» (“neural network”) or «правила» (“rules”) — the kind of model; «в памяти» (“in memory”) — the model is loaded in the running process; «изменено» (“modified”) — the administrator's decision differs from the value in the settings file; «изменено: имя» (“modified: name”) — who changed the setting last; «файл не найден» (“file not found”) — the artifact is missing on disk at the given path; «работает поверх модели «…»» (“runs on top of model …”) — the model uses the results of another one; «не сработает, пока выключена «…»» (“will not work while … is disabled”) — the model is blocked by a disabled dependency.

The file path and its size in megabytes are shown right on the card — this is the fastest way to make sure the artifact is in place.

### 6.4 Unloading from memory

The «Выгрузить» (“Unload”) button frees memory without disabling the model. The button is available only for neural networks whose artifact is actually found on disk.

| Rule | What happens |
|---|---|
| Encoder | Unloaded together with the classifier: without it there is nothing to run the classifier on |
| Classifier | Unloaded separately and weighs less than a megabyte — it can be removed from memory without touching the encoder |
| Work volume estimation | Cannot be unloaded: it is a set of rules, they do not occupy memory, and the server explains the refusal |
| Repeated loading in the same process | Unreliable: the freed block is retained by the allocator |
| What to do after unloading | Click «Загрузить» (“Load”) in the page header or restart the server |

Unloading is appropriate when the models are needed rarely and memory is required for other tasks. Keep in mind that after unloading the first call to the model is slow: the weights are read from disk again.

### 6.5 Warm-up at startup

Loading the weights takes seconds, so the model is warmed up by a background task at server startup and does not block the application from starting. The models are loaded lazily: a disabled model does not read the weights and does not pull in heavy dependencies at all — the server runs without the artifacts too.

The conditions for the background warm-up at startup must all be met at the same time:

1. code analysis models are allowed in the settings file;
2. commit type detection is allowed in the settings file;
3. the encoder is enabled taking the decision from the database into account.

A consequence: if you have disabled commit type detection in the settings file, the background warm-up at startup will not run, even if these models are enabled in the panel. The model will come up lazily — on the first call, that is, when it is already needed. For predictable behaviour keep the settings file flags enabled.

Manual warm-up: the «Загрузить» (“Load”) button in the page header re-reads the decisions from the database and warms up the enabled models. If the encoder is disabled, the server will answer that warm-up was skipped — this is normal behaviour, not an error.

### 6.6 Diagnostic endpoints and their access restriction

To verify a deployment there are two service requests that are made directly to the server, bypassing the interface:

| Request | What it does |
|---|---|
| `GET /api/v1/ai/code-model/status` | Returns the state: whether the model is enabled, whether the artifacts are in place, whether it is loaded in memory, and on which device it runs |
| `POST /api/v1/ai/code-model/load` | Warms up the model and returns the same state |

What the state shows:

| Field | Value |
|---|---|
| Availability flag | Whether the model is fully ready to work |
| Reason for unavailability | `disabled`, `tokenizer_missing`, `tracer_missing`, `classifier_missing`. For the classifier, additionally `encoder_disabled` |
| Artifact readiness | Separately for the tokenizer folder, the encoder weights, and the classifier weights |
| Which files are missing | A list of missing tokenizer files |
| Whether it is loaded in memory | Separately for the encoder and the classifier |
| Device | `cpu` or `cuda` |
| Link threshold | The current value of the threshold for matching a commit to a task |
| Commit types | A list of supported types |

> **Access restriction.** These two requests, as well as the manual trace
> and commit type detection requests, **require no authorization**: they are
> available to anyone who reaches the server address, including an anonymous
> visitor. They are not called from the user interface — they are used
> manually.
>
> What this gives an attacker: information about which model files are in
> place, whether memory is occupied, and which thresholds are configured.
> They do not expose user data.
>
> Recommendation: **close these paths at the reverse proxy level** (a deny
> rule by route) or restrict external access to the server. An authorized
> equivalent of your own exists in the panel:
> «Управление нейросетевыми моделями» (“Neural model management”).

---

## 7. Storage and limits

The «Управление хранилищем» (“Storage management”) section controls how much space attachments may occupy, how long they stay after deletion, and what happens when the quota is exceeded. All settings are stored in the database and applied without a restart: they are re-read on every file upload and on every trash cleanup pass.

### 7.1 What occupies space

| Metric | What it counts |
|---|---|
| Total on disk | The sum of the three rows below |
| Active | Attachments attached to tasks |
| «Корзина» (“Trash”) | Attachments marked deleted but still lying on disk |
| «Неприкреплённые» (“Unattached”) | Files uploaded but not linked to any comment |

An important clarification: the summary includes **only task attachments**. User avatars and project backgrounds occupy space in the same storage directory but are not reflected in these numbers. If the directory grows faster than the numbers show, look for the discrepancy in these files.

### 7.2 Attachment limits and project limits

The «Лимиты вложений» (“Attachment limits”) block:

| Setting | Allowed range | Default | What it does |
|---|---|---|---|
| «Максимальный размер файла» (“Maximum file size”) | 1…1024 MB | 25 MB | Larger files are rejected on upload |
| New project limit | 1…102400 MB | 500 MB | Applies to projects without their own limit |
| «Разрешённые расширения» (“Allowed extensions”) | list | `.png,.jpg,.jpeg,.gif,.pdf,.doc,.docx,.txt,.zip,.log` | Files of other types are rejected on upload |

The extension list is entered comma-separated: the leading dot is added automatically, duplicates are removed, and the order is sorted. An empty list cannot be saved — such a setting would make uploads impossible. The «Сохранить» (“Save”) button is active only when there are unsaved changes; the server rejects values outside the range and shows the allowed limits.

The «Проекты» (“Projects”) block — individual quotas:

| Action | What happens |
|---|---|
| «Задать» (“Set”) with a value in MB | The project gets its own limit |
| «Вернуть общий» (“Restore shared”) | The project returns to the shared limit from the settings |
| Fill bar | Green up to 60 %, amber from 60 to 90 %, red from 90 % |
| «общий лимит» (“shared limit”) badge | Shown for projects without their own limit |

Projects are sorted by decreasing usage: the “heaviest” ones at the top.

### 7.3 Trash and auto-cleanup

| Setting or action | Allowed range | Default | What it does |
|---|---|---|---|
| Retention period | 0…365 days | 7 days | After how many days deletion becomes irreversible |
| «Проверять корзину (интервал)» (“Check trash (interval)”) | 1…168 hours | 6 hours | How often auto-cleanup runs. The field is disabled if auto-cleanup is off |
| «Очищать автоматически» (“Clean automatically”) | — | Enabled | The background task starts together with the server |
| «Очистить просроченное» (“Clean expired”) | — | — | Deletes only what has passed the retention period |
| «Очистить корзину целиком» (“Empty trash completely”) | — | — | Deletes everything in the trash regardless of the period, after confirmation |

Below the period field a counter is shown: how many records are already older than the retention period and will disappear at the next auto-cleanup. The «Очистить просроченное» (“Clean expired”) button is active only when such records exist.

**The main thing an administrator must understand:** deleting an attachment does not delete the file from disk. The attachment is only marked deleted and goes to the trash; the file itself keeps occupying space until the trash is cleaned. Space in the project quota is also freed during cleanup, not at the moment of deletion.

An upload first creates a record with the status «неприкреплён» (“unattached”), and linking to a comment happens later. If the link never happens, the record is deleted after 24 hours — but only during background cleanup.

### 7.4 What happens when the quota is exceeded

On file upload the checks run strictly in this order:

| Order | Check | What the user sees on rejection |
|---|---|---|
| 1 | File size | A message about exceeding the maximum size, with the limit stated |
| 2 | Extension | A message about an invalid file type with the list of allowed ones |
| 3 | Project quota | A message about reaching the project's storage limit |

The project's usage counter increases only after a successful upload, so failed attempts do not consume the quota.

A calculation detail: the project limit is the individual one if it is set; otherwise the shared limit from the settings is used. Projects created before the shared limit was changed automatically fall under it, but their individual limits remain in force. If users complain about unexpected rejections, check the current limit values here and the usage of a specific project by the fill bar.

---

## 8. Logs and audit

The system has four sources of history. None of them is a complete log of administrator actions — this is stated honestly at the end of the section.

### 8.1 Task activity log

Every change to a task is recorded as a separate entry. Ten event types are recorded:

| Event type | When it appears |
|---|---|
| Task creation | The card is created |
| Status change | The task is moved between columns |
| Assignee change | An assignee is set or cleared |
| Priority change | The priority is changed |
| Comment added | A comment is posted |
| Subtask added | An item is added to the checklist |
| Subtask status change | A checklist item is checked |
| Subtask deleted | A checklist item is deleted |
| Attachment added | A file is uploaded to the task |
| Attachment deleted | The file is marked deleted |

Where to look: the «История» (“History”) tab in the task card and the «История» (“History”) tab on the project board. The entries contain the author, the time, and a description of the change.

### 8.2 Git event log

Events that arrive from the provider through a webhook land in the Git event log together with a mark of whether the event signature passed. The log is visible in the project activity feed and in the task history. For an administrator this is the main source for investigation: “did events arrive at all” and “were they accepted”.

### 8.3 Events without a link

Events that could not be matched to a task land in a separate list: project settings → the «Непривязанные события» (“Unlinked events”) tab. Such an event can be linked to a task manually right from there. A large number of unlinked events means that the link parsing rules are not firing — usually because of a different commit message format in that repository.

### 8.4 Who changed the settings and when

| What | Where it is stored | Where it is visible |
|---|---|---|
| Model settings | The author name and the modification time | The «изменено: имя» (“modified: name”) badge on the models page |
| Storage settings | The author of the change is stored in the database | **Not displayed in the interface** |

If you need to know who changed the limits, look at the records in the database directly.

### 8.5 What is missing: a log of administrator actions

**There is no separate log of administrator actions in the system.** This is missing functionality, not a configuration restriction. Not logged: granting and revoking administrator rights; blocking and deleting accounts; changing roles and role permissions; changing storage limits and trash settings; changing model settings (only the author and the time are stored, with no history of “from which value to which”); adding, changing the role of, and removing project participants through the admin panel.

What to do instead:

- enable server logs and keep them: errors of background tasks and storage maintenance are recorded there;
- agree on a rule: one responsible person changes the settings, and significant edits are recorded in the organisation's internal log;
- in an incident, rely on the logs from sections 8.1–8.3 and on the author badge of the model settings.

---

## 9. Deployment

This section describes production deployment. Everything listed here is
required for a working installation available to users.

### 9.0 Production launch: the short order

| Step | What to do | How to verify |
|---|---|---|
| 1 | Bring up the database and Redis | `docker compose ps` — both services are “healthy” |
| 2 | Copy `backend/.env.example` to `backend/.env` and set `SECRET_KEY` | The file exists, the key is not equal to the default value |
| 3 | Build the server image | `docker compose build backend` |
| 4 | Apply the migrations | `docker compose run --rm backend alembic upgrade head` |
| 5 | Start the server | `docker compose up -d backend`, then `docker compose logs -f backend` |
| 6 | Change the first administrator's password (section 9.3) | Signing in with the new password succeeds |
| 7 | Set `PUBLIC_BASE_URL` to the external address | The repository connection check in the project settings passes |
| 8 | Serve the frontend and point the proxy at it | The frontend opens at the external address |

The order is not arbitrary. Migrations run **before** the first login:
otherwise the server comes up on an empty schema. The external address is set
**before** connecting repositories: webhook addresses are built from it, and
changing the address after registering webhooks means re-registering them.

### 9.1 How the production mode differs from the development mode

The difference is not cosmetic: in development mode part of what would break
in production simply does not run.

| What | Development | Production mode |
|---|---|---|
| Server startup | `uvicorn app.main:app --reload` | `uvicorn app.main:app` without `--reload`; the server does not restart itself when files are edited and does not read the sources in hot mode |
| Frontend | `npm run dev`, port 3000, proxy to the development server | `npm run build` and serving the built files by a web server |
| Server port | 8000, opened externally for debugging | Closed: only the proxy that serves the frontend is exposed |
| Debug mode | Enabled | Disabled |
| Model artifacts | In the project folder | Connected by mounting or copied into the image |
| Cross-origin requests | Allowed from anywhere | Restricted by the proxy (section 9.2.3) |

### 9.1.1 Serving the frontend

The server serves the application's programmatic interface, not the static assets
of the frontend. The frontend is built separately and served by a web server in
front of the application server.

Build:

```bash
cd frontend
npm ci
npm run build
```

The output is the `frontend/dist` folder. It must be served by a web server
that:

1. serves `frontend/dist` as the site root;
2. redirects any unknown addresses to `index.html` — otherwise following a
   direct link inside the application will fail;
3. redirects requests to `/api/`, `/uploads/` and `/manuals/` to the application
   server;
4. issues a certificate if access is over HTTPS.

The redirect block looks like this:

```
location /api/    { proxy_pass http://127.0.0.1:8000; }
location /uploads/ { proxy_pass http://127.0.0.1:8000; }
location /manuals/ { proxy_pass http://127.0.0.1:8000; }
location /        { try_files $uri $uri/ /index.html; }
```

> Close the `/api/v1/ai/code-model/` routes from outside — they require no
> authorization and show the state of the models (section 6.6).

### 9.1.2 Model artifacts in production mode

The server image is built **without** the model weights: the encoder weighs
about a gigabyte, and there is no reason to put it in the image on every run.
The artifacts are connected separately and survive a rebuild of the image.

Put the files in a folder outside the repository; the layout repeats the model
structure in the project:

```
models/code_model/commit_tracer.pt
models/code_model/type_classifier.pt
models/code_model/paraphrase-multilingual-mpnet-base-v2/
```

Then in `docker-compose.yml` uncomment the mount and set
the root:

```yaml
    environment:
      CODE_MODEL_DIR: /app/models
    volumes:
      - ./models:/app/models:ro
```

The mount is read-only: the server does not modify the artifacts, and an
accidental write into the mounted folder must not corrupt manually replaced files.

If the server is started without Docker, the same path is set in `backend/.env`.

### 9.1.3 Check after deployment

| What to check | How |
|---|---|
| The server responds | `docker compose ps` — the server is “healthy”; or `curl` to `http://127.0.0.1:8000/` |
| The database schema is in place | `docker compose exec backend alembic current` |
| The models load | `curl` to `http://127.0.0.1:8000/api/v1/ai/code-model/status` |
| The artifacts are in place | Same place: the «Готовность артефактов» (“Artifact readiness”) section for the encoder and the classifier |
| The frontend is open | Open the external address in a browser |
| Repository connection check | Project settings → Git tab → «Проверка подключения» (“Connection check”) |

While the models module is not loaded, the server works: code analysis is
simply not performed. This is deliberate behaviour, not a failure — see section 6.1.

### 9.1.4 Requirements

Two deployment options: Docker Compose — three services are brought up (a PostgreSQL 16 database, Redis 7, and the application server on port 8000); manual installation — Python 3.10 or newer, Node.js 18 or newer, PostgreSQL, and Redis.

Resources: about 1.1 GB of disk for the model artifacts, if they are used, and about 1.6 GB of RAM above the usual consumption with the encoder loaded. A video card is not required: the models run on CPU, the default setting is auto-detection, and if resources are short you can force CPU. Git is needed both by the server and by users.

### 9.2 Environment variables

The variables file is `.env` in the working directory of the server process. Names are case-sensitive: `SECRET_KEY` and `secret_key` are different things, a typo in the case silently leaves the default value. The `docker-compose.yml` file passes only two variables into the container — the database connection and the Redis connection; the server reads all the others from the file, which must end up inside the container.

#### 9.2.1 General settings and the database

| Variable | Default | Purpose |
|---|---|---|
| `PROJECT_NAME` | `Kipatik` | The application name in the documentation title and in the root address response |
| `API_V1_STR` | `/api/v1` | The prefix of all programmatic interface addresses |
| `DATABASE_URL` | `postgresql+asyncpg://user:password@db:5432/diplom` | Database connection |

#### 9.2.2 Redis and task queues

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Background task broker |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` | Storage of background task results |

The default values are designed for deployment via Compose. For a manual installation, specify the real addresses of your Redis instances.

#### 9.2.3 Security

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `SUPER_SECRET_KEY_CHANGE_ME` | The signing key for login tokens and the base encryption key for Git tokens |
| `ALGORITHM` | `HS256` | The token signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `604800` (7 days) | The lifetime of a login token |
| `TOKEN_ENCRYPTION_KEY` | empty | The encryption key for Git provider tokens in storage |

> **Cross-origin requests are allowed from anywhere.** The server accepts
> requests from any address, with any methods and headers. While the client
> and the server stand on the same address or nearby, this is harmless. As
> soon as the server is exposed to the internet, restrict the list of allowed
> origins at the reverse proxy: an open list means that the page of your
> application can be opened from a foreign domain and the API can be called from there on behalf of the signed-in user.

> **`SECRET_KEY` must be replaced.** The default value is widely known: anyone
> can forge a login token and sign in with administrator rights. Set a random
> string of sufficient length.
>
> **`TOKEN_ENCRYPTION_KEY` and `SECRET_KEY` are linked.** If the encryption key
> is not set explicitly, it is derived from `SECRET_KEY`. Therefore:
>
> - if Git provider tokens **have not been stored yet** — you can set
>   `SECRET_KEY` and not set `TOKEN_ENCRYPTION_KEY`;
> - if tokens **are already encrypted and stored** — you **must not change
>   `SECRET_KEY` or `TOKEN_ENCRYPTION_KEY`**. The stored tokens will stop
>   being decryptable, all connected Git accounts will stop working, and
>   users will have to connect them again.
>
> Practical conclusion: set both keys explicitly and store them in a safe
> place **before** the first repository connections.

#### 9.2.4 Periodic Git sync

| Variable | Default | Purpose |
|---|---|---|
| `GIT_SYNC_ENABLED` | `True` | Enable the background repository sync |
| `GIT_SYNC_INTERVAL_SECONDS` | `300` | Background sync interval |
| `GIT_SYNC_MAX_PAGES` | `5` | How many data pages are fetched in one pass |
| `GIT_SYNC_PAGE_SIZE` | `100` | Page size during fetching |
| `GIT_SYNC_SINCE_DAYS` | `90` | History depth on the first sync |
| `GIT_HTTP_TIMEOUT_SECONDS` | `20.0` | Timeout for requests to the provider |
| `GIT_HTTP_MAX_RETRIES` | `3` | How many retries on errors |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Public server address: the webhook address is built from it |
| `GIT_WEBHOOK_AUTO_REGISTER` | `True` | Automatic webhook registration through the provider's programmatic interface |

`PUBLIC_BASE_URL` is the address of the **server**, not of the frontend. The webhook address is built as `{PUBLIC_BASE_URL}/api/v1/git/webhook/{repository identifier}`. If the server stands behind a proxy, this must be the address that is reachable by the provider from outside.

#### 9.2.5 Provider OAuth applications

| Variable | Default | Purpose |
|---|---|---|
| `GITHUB_CLIENT_ID` | empty | GitHub OAuth application |
| `GITHUB_CLIENT_SECRET` | empty | GitHub OAuth application secret |
| `GITLAB_CLIENT_ID` | empty | GitLab OAuth application |
| `GITLAB_CLIENT_SECRET` | empty | GitLab OAuth application secret |
| `GITLAB_HOST` | `https://gitlab.com` | GitLab address; specify your own server |
| `GITEA_CLIENT_ID` | empty | Gitea OAuth application |
| `GITEA_CLIENT_SECRET` | empty | Gitea OAuth application secret |
| `GITEA_HOST` | empty | Gitea address |
| `BITBUCKET_CLIENT_ID` | empty | Bitbucket OAuth application |
| `BITBUCKET_CLIENT_SECRET` | empty | Bitbucket OAuth application secret |
| `OAUTH_FRONTEND_REDIRECT` | `http://localhost:3000/profile` | The address of the **frontend**, where the provider returns the user |
| `OAUTH_STATE_TTL_SECONDS` | `600` | The lifetime of the signed confirmation parameter |

While these variables are empty, a fallback path is available — manual entry of a personal access token. It always works, but it requires the user to issue the token in the provider settings themselves.

#### 9.2.6 Work volume estimation

| Variable | Default | Purpose |
|---|---|---|
| `PROGRESS_ENABLED` | `True` | Enable the work volume estimation module |
| `PROGRESS_DEFAULT_EXPECTED_VOLUME` | `200` | Expected volume of changes per task in lines, when there is nothing to calibrate against |
| `PROGRESS_MIN_TASKS_FOR_CALIBRATION` | `3` | How many tasks with commits are needed to trust the calibration per project |
| `PROGRESS_CALIBRATION_PRIOR_STRENGTH` | `3` | Prior strength: the data weight equals `n / (n + strength)`, where `n` is the number of observations |
| `PROGRESS_HISTORY_DAYS` | `30` | How many days to show in the progress dynamics |

#### 9.2.7 Code analysis models

| Variable | Default | Purpose |
|---|---|---|
| `CODE_MODEL_ENABLED` | `True` | Master switch for code analysis models; the default value for the encoder |
| `CODE_MODEL_DIR` | empty — search next to the code | The root in which the model folders live. Set it only if the artifacts are not there |
| `CODE_MODEL_TRACER_FILE` | `commit_tracer.pt` | The encoder weights file name |
| `CODE_MODEL_CLASSIFIER_FILE` | `type_classifier.pt` | The classifier weights file name |
| `CODE_MODEL_DEVICE` | `auto` | Compute device: `auto`, `cpu`, or `cuda` |
| `CODE_MODEL_TRACE_THRESHOLD` | `0.30` | Threshold for linking a commit to a task. Below the threshold the decision stays with the person |
| `CODE_MODEL_TRACE_LIMIT` | `20` | How many project tasks to consider when matching |
| `CODE_MODEL_TRACE_BUDGET_SECONDS` | `5.0` | Time budget for one commit in a bulk run |
| `GIT_TRACE_ON_SYNC` | `False` | Tracing by meaning during the background sync |
| `GIT_TRACE_SYNC_LIMIT` | `10` | How many commits to trace in one pass |
| `GIT_TRACE_FETCH_PATCHES` | `False` | Whether to fetch the diff texts right during tracing |
| `CODE_MODEL_CLASSIFY` | `True` | Determine the commit type when linking to a task |

The values of these variables are only the **defaults**. Once you have made a decision on the models page, the database decides, not the file (section 6.3); the «изменено» (“modified”) badge shows where the decisions differ.

The artifacts of both models lie in one folder `app/ai/code_model`:

```
app/ai/code_model/commit_tracer.pt                      веса трассировки
app/ai/code_model/type_classifier.pt                    веса типов
app/ai/code_model/progress_estimator.py                 модуль правил
app/ai/code_model/paraphrase-multilingual-mpnet-base-v2/  конфиг и словарь
```

`CODE_MODEL_DIR` sets the root inside which the `code_model` folder is searched for. An empty value means “search next to the code”: the path does not depend on which folder the server was started from. In a container, set it explicitly if the artifacts are connected by mounting — for example `/app/models`.

#### 9.2.8 Diff texts

| Variable | Default | Purpose |
|---|---|---|
| `GIT_FETCH_PATCHES` | `False` | Whether to request the diff texts from the provider |
| `GIT_MAX_PATCH_CHARS` | `4000` | Maximum number of characters of the diff text per file |
| `GIT_PATCH_BACKFILL_LIMIT` | `50` | How many commits to backfill in one pass |
| `GIT_PATCH_BACKFILL_DELAY` | `0.3` | Pause between requests so as not to hit the provider limits |

Diff texts are disabled by default intentionally: this is a separate request to the provider for every commit, and enabling it on a large project turns the sync into hundreds of requests. The models are noticeably more accurate when the diff texts are filled in, so on projects where tracing accuracy matters, the backfill is worth enabling and filling in advance.

#### 9.2.9 Manuals

| Variable | Default | Purpose |
| --- | --- | --- |
| `SERVE_DOCS` | `false` | Enables serving the manuals at `/manuals/<filename>` |
| `DOCS_DIR` | determined automatically | The folder with the manual texts |

The texts lie in the `docs/` folder next to the `backend` folder — two guides each, in Russian and in English:

```
docs/user-guide.md          docs/admin-guide.md
docs/user-guide.en.md       docs/admin-guide.en.md
```

These are the only copies of the files: the very same files are opened by Git and by the help page inside the application, so two copies of the text cannot diverge.

The language is substituted according to the interface language. If the English guide is placed next to the Russian one, the help page will open the right one by itself; if it is missing — the page will show a load error.

The help page is opened from the header **in a new tab**: reading a guide must not take you away from the board you were working on.

`DOCS_DIR` usually does not need to be set. The application searches for the folder next to itself, then in the repository root. The value is required in a container, where the folder structure is different: there the texts are copied to `/app/docs`, and the variable is already set in the image.

Serving the manuals is disabled by default intentionally: this guide contains secrets and a list of environment variables. Enable it only inside a perimeter where access to such files is acceptable, and disable it again afterwards.

The `/docs` address is occupied by the built-in API documentation and has nothing to do with the manuals.

> **Important: the application will not start with any unknown environment variable.**
> The settings are loaded with extra fields forbidden, so an unknown variable in `.env` or in the container environment aborts startup with a validation error rather than being ignored. If the server does not start and the error text mentions “extra inputs”, look for a typo or an obsolete variable in `.env` and in `docker-compose.yml`. This also applies to variables that used to be read manually: new ones have to be added to the application settings, otherwise they will not work.

### 9.3 First startup and the first superuser

On the first server startup, if the database has no user with identifier 1, the following account is created automatically:

| Field | Value |
|---|---|
| Email | `admin@example.com` |
| Password | `admin` |
| Full name | `Default Admin` |
| Administrator rights | Yes |
| Permission to create projects | Yes |

At the same time a message about the creation of the default user is printed to the startup log.

> **You must change the password immediately after the first sign-in.**
>
> The credentials `admin@example.com` / `admin` are published in the project
> documentation and are known to anyone who has gained access to your server.
> Until the password is changed, any visitor can sign in with full administrator
> rights, grant those rights to themselves and others, disable the models,
> change the storage limits, and delete other people's data.
>
> Order of actions: sign in with that account → «Управление пользователями»
> (“User management”) → the pencil next to yourself → set a new password →
> save. The password field can be left empty when editing if you do not need to change it.

What you **cannot** do: set these credentials through the settings file. The application has no variables for the login and password of the first administrator, and they have to be added to the settings — a new variable read directly will not work (section 9.2.9). The login and password of the first administrator are hard-coded in the source code.

Additionally: the check is performed by identifier, not by email. If the account with identifier 1 was deleted, it will be created again with the same data on the next server startup. This is one more reason to check the password.

### 9.4 Database migrations

The database schema is applied by migrations once at deployment time. The server intentionally does **not** run migrations on startup: a second instance of the application restarting must not change the schema of someone else's database.

Order of actions: (1) bring up the database and Redis; (2) build the server image — with the `torch` install build argument if needed; (3) start the server container; (4) run `docker compose exec backend alembic upgrade head`; (5) make sure the server responds and sign in as the first administrator.

For a manual installation, step 4 is performed from the server directory with `alembic upgrade head`, and startup with `uvicorn app.main:app --reload` for development. Back up the database **before** the update: migrations are irreversible.

### 9.5 Provider tokens and OAuth

| Method | When to use | What is required |
|---|---|---|
| OAuth application | Preferred: the user clicks a button once | Register the application with the provider and fill in the variables from section 9.2.5 |
| Personal token | Until OAuth is configured | The user issues the token with the provider themselves |

Order of the OAuth setup:

1. Register the application with the provider and obtain the identifier and the secret.
2. Fill in the corresponding variables from section 9.2.5 and restart the server.
3. Use the address of the **server** as the return address: `{PUBLIC_BASE_URL}/api/v1/auth/oauth/{provider}/callback`.
4. Check `OAUTH_FRONTEND_REDIRECT` — it is the address of the **frontend**, and by default it points at the development mode.

The webhooks on the provider side must accept `push` and `pull_request` events. The system issues the webhook address in the project settings on the Git tab; with `GIT_WEBHOOK_AUTO_REGISTER` enabled the system tries to register the webhook itself through the provider's programmatic interface — for this the provider must have granted permissions to manage webhooks.

---

## 10. Maintenance

### 10.1 Background Git sync

The server itself periodically walks through all connected repositories and fetches commits, branches, and merge requests. This task runs **inside the server process**: a separate task queue worker is not needed for it, and the queue schedule is not configured in the project.

| Parameter | Value | How to change |
|---|---|---|
| Whether it is enabled | Yes | `GIT_SYNC_ENABLED` in the settings file |
| Interval | 5 minutes | `GIT_SYNC_INTERVAL_SECONDS` in the settings file, restart of the server |
| Depth of the first sync | 90 days | `GIT_SYNC_SINCE_DAYS` |
| Fetch depth per pass | 5 pages of 100 records each | `GIT_SYNC_MAX_PAGES`, `GIT_SYNC_PAGE_SIZE` |

Signs that the sync is working: in the project settings on the Git tab the time of the last sync and its status are visible; new commits appear in the project history without any actions from users.

### 10.2 Background backfill of diffs and types

A separate background processing starts on a manual repository sync (the «Синхронизировать» (“Synchronize”) button in the project settings → Git) and goes in three steps:

| Step | What it does | When it runs |
|---|---|---|
| 1 | Backfills the diff texts for commits that do not have them | If `GIT_FETCH_PATCHES` is enabled |
| 2 | Picks tasks for unlinked commits by meaning | If `GIT_TRACE_ON_SYNC` is enabled |
| 3 | Recomputes the commit types for those whose type was not determined at the moment of linking | If the code analysis models are allowed |

The process is time-limited: the request waits for the end of the processing, but no longer than 90 seconds. If the model computes longer, the user is shown the «идёт разбор» (“processing”) state, and the result becomes visible later — when the settings are reopened. This is expected behaviour, not a hang.

Keep step 3 in mind when investigating “why does a commit have no type”: the type is recomputed only for already linked commits and only after the model has become available.

### 10.3 Automatic trash cleanup

The background cleanup task starts at server startup, only if auto-cleanup is enabled in the panel. The interval is taken from the «Проверять корзину» (“Check trash”) setting and is re-read on every pass — changing the interval does not require a restart. In one pass the task:

1. deletes unattached files older than 24 hours;
2. deletes from the trash everything older than the retention period;
3. recalculates the space usage for the affected projects.

If auto-cleanup is turned off, the first step stops running as well: unattached files will accumulate and hold space in the project quotas. If you need control over the deletions but such records still have to be cleaned, empty the trash manually with the «Очистить корзину целиком» (“Empty trash completely”) button.

### 10.4 If the model does not load

| Step | Check | What to do if there is a problem |
|---|---|---|
| 1 | Open «Управление нейросетевыми моделями» (“Neural model management”) | Look at the «файл не найден» (“file not found”) badge and the file path |
| 2 | Check the tokenizer folder | It must lie next to the weights and contain five files; without it the model will not start |
| 3 | Check the `torch` installation | It is installed separately; in the image it is enabled with a build argument |
| 4 | Look at the state through the diagnostic request | The reason for unavailability decodes the problem: disabled, no tokenizer folder, no encoder or classifier weights |
| 5 | Check the available memory | The encoder requires about 1.6 GB; if memory is short, the load aborts |
| 6 | Check the device setting | With automatic selection the server may take the video card; if resources are short, specify `cpu` |
| 7 | Click «Загрузить» (“Load”) on the models page | Warm-up of the enabled models again |
| 8 | Restart the server | Helps after unloading: repeated loading in the same process is unreliable |

### 10.5 Logs

The server writes logs to standard output, that is, to the container or service log.

What ends up in the logs: the creation of the default user on the first startup; the readiness of the code analysis model and its load time, as well as an unsuccessful warm-up with the reason; the start and stop of the background sync and cleanup cycles; the results of the trash cleanup passes and of the deletion of unattached files; unhandled errors of the background cycles; errors accessing the model and storage settings when the database is unavailable; errors of the background repository processing with the step indicated.

When the settings database is unavailable the server does not crash: it writes a warning and keeps working with the default values. The storage settings follow the same logic. This is convenient for resilience, but it means that your settings may silently not apply — when in doubt, check against the panel and the log.

---

## 11. Diagnostics

### 11.1 Models

| Symptom | Likely cause | What to check |
|---|---|---|
| The «файл не найден» (“file not found”) badge | The artifact is missing at the given path | The path on the model card; whether the file exists; whether the artifact directory is set correctly in the settings file |
| Reason `tokenizer_missing` | No tokenizer folder or some of its files | Whether the five tokenizer files are present next to the weights |
| Reason `tracer_missing` | No encoder weights file | Whether the file exists and its size (about 1 GB) |
| Reason `classifier_missing` | No classifier weights file | Whether the file exists; without it the model as a whole is considered unavailable, even if the encoder is in place |
| Reason `disabled` | The encoder is disabled | The state of the power button and the «изменено» (“modified”) badge on the card |
| The model is enabled but not “in memory” | Warm-up did not run or the model was unloaded | The «Загрузить» (“Load”) button; on refusal — the error entry in the logs |
| A load error while the files are present | `torch` is not installed | Whether `torch` is installed; for a container — a rebuild with the install build argument |
| The model crashes when running on a video card | Insufficient video memory | Set the device to `cpu` in the settings file and restart |
| Linking does not work although the models are enabled | The diff texts are not loaded | Enable the backfill of the diff texts; the state of the background repository processing |
| After «Выгрузить» (“Unload”) the model does not come up | Repeated loading in the same process is unreliable | Click «Загрузить» (“Load”) or restart the server |
| After startup the model is not warmed up | The background warm-up condition was not met | The model and type detection flags in the settings file, the encoder state in the panel (section 6.5) |

### 11.2 Git integration

| Symptom | Likely cause | What to check |
|---|---|---|
| Commits do not appear | The webhook is not configured | Project settings → Git → the connection check: are all four steps checked |
| The webhook is configured, but events do not arrive | The webhook address is not reachable from outside | The public server address in the settings file; whether the webhook address is open from the internet |
| Events arrive, but the signature does not pass | Mismatch of the secrets | Re-register the webhook in the project settings and enter the new secret with the provider |
| Commits are not linked to tasks | The message format does not match the expected one | Project settings → unlinked events; is their number large |
| Commits are linked to the wrong task | The matching threshold is too low | The link threshold in the settings file: a low value gives extra links |
| The model suggests a link, the person does not agree | This is expected: below the threshold the decision stays with the person | The link threshold and the confidence marks in the task history |
| The commit type is not determined | The model was not available at the moment of linking | Run «Синхронизировать» (“Synchronize”) — the types are recomputed for already linked commits |
| «Идёт разбор» (“Processing”) does not disappear | The background processing runs longer than 90 seconds | Wait and refresh the settings: the processing state and its error are shown there |
| The repository is connected, but there is no data | The background sync has not run yet | Wait up to 5 minutes or click «Синхронизировать» (“Synchronize”) |
| Synchronization ended with an error | The token has expired or there are not enough permissions | The error text of the last synchronization; the account connection state in the profile |

### 11.3 Storage

| Symptom | Likely cause | What to check |
|---|---|---|
| The upload is rejected with a size error | The file is larger than the maximum size | «Управление хранилищем» (“Storage management”) → «Максимальный размер файла» (“Maximum file size”) |
| The upload is rejected with a type error | The extension is not in the allowed list | «Разрешённые расширения» (“Allowed extensions”); the dot is added automatically |
| The upload is rejected with a quota error | The project has exhausted its limit | The fill bar of the project; if necessary, raise the individual limit |
| Disk space is not freed | The deleted files lie in the trash | «Корзина» (“Trash”) and «Очистить просроченное» (“Clean expired”); the default retention period is 7 days |
| Space is freed more slowly than expected | Auto-cleanup is off or a long interval is set | The «Очищать автоматически» (“Clean automatically”) checkbox and the «Проверять корзину» (“Check trash”) field |
| The quota differs from the actual usage | The counter is recalculated during cleanup | Run the trash cleanup — the usage is recalculated for the affected projects |
| The panel shows values you did not set | The settings database was unavailable, the default values apply | The entry about the unavailability of the storage settings in the server logs |
| Files uploaded “nowhere” occupy space | Unattached records older than 24 hours are deleted in the background | The «Неприкреплённые» (“Unattached”) state in the summary; whether auto-cleanup is working |

### 11.4 Access and accounts

| Symptom | Likely cause | What to check |
|---|---|---|
| The admin panel is unavailable, return to the home page | The user has no administrator rights | The «Админ» (“Admin”) column in «Управление пользователями» (“User management”) |
| A request to an administrative section is rejected with 403 | No permissions on the server | The server checks the permissions independently of the interface |
| You cannot remove the rights from yourself or delete yourself | Protection against losing the only administrator | Expected behaviour; appoint a second administrator in advance |
| A user has lost access | The account is blocked | The «Статус» (“Status”) column; the same toggle removes the block |
| Editing a role had no effect | There is no record of that role in the database — the built-in matrix applies | Check that the role exists in «Управление ролями» (“Role management”) (section 4.3) |
| The role is deleted, but the participants are left without rights | The rights were taken from the built-in matrix | Remove the participants from the role before deleting it |
| A user with the required email cannot be created | That address is already taken | The search in «Управление пользователями» (“User management”) |

### 11.5 Deployment and the server

| Symptom | Likely cause | What to check |
|---|---|---|
| The documentation page does not open | The server is not running or the port is closed | The server address on port 8000; the container state |
| Database connection error | Wrong connection string or the database is unavailable | The database connection variable; the state of the database container |
| Error when accessing Redis | Redis is not running or the address is wrong | The Redis variables; the state of the Redis container |
| “Tables do not exist” | Migrations are not applied | Run the migration command from section 9.4 |
| The server starts with unexpected settings | The variables are not read: a typo in the name or the case, or the file is not in the working directory | The variable names with the case taken into account; the working directory of the process |
| Background tasks do not run | A separate task queue worker is running, and the server process has not been restarted | The background cycles live inside the server process; restart exactly that one |
| The manuals do not open at the documentation address | Serving the manuals is disabled by default | The serving switch variable; enable it only inside a protected perimeter |

---

## 12. Known limitations

An honest list of what the system does not have or what does not work fully.

### 12.1 Administration

| Limitation | Consequence |
|---|---|
| There is no log of administrator actions | You cannot find out who granted the rights, blocked a user, or changed the limits or roles, and when. For model settings only the author and the time of the last change are stored |
| Storage settings store the author but do not display them | Who changed the limits and the retention period cannot be found out from the interface |
| There is no history of settings changes | Only the current value is visible and, for models, the author of the last change |
| The label and tag management permissions are granted, but there are no labels in the system | Neither the model, nor the interface, nor any rules for working with labels exists |
| The permission to manage project rules cannot be granted | It is missing both from the panel permission list and from the system itself |
| The user list is limited to a hundred records with no pagination | On large systems the full list is not displayed without the search |
| Deleting an account does not delete the projects it owned | The project remains without an owner able to manage it |
| Changing a participant's role in the regular participants window does not work | Only the admin path works (section 5.4) |

### 12.2 Security

| Limitation | Consequence |
|---|---|
| Model diagnostic requests are available without a permission check | Information about the model files, memory, and thresholds is exposed; close the routes on the proxy (section 6.6) |
| Cross-origin requests are allowed from any address | A risk when working from a browser with external addresses; restrict it at the proxy level |
| The first administrator's password is not configurable | The credentials are known in advance; changing the password after the first login is mandatory |
| The security key linkage | Changing the encryption key or the signing key after the Git tokens are saved breaks them; set both explicitly and in advance |
| The guide with the default secrets is not served by the server | A deliberate restriction; enable serving only inside a protected perimeter |

### 12.3 Functionality

| Limitation | Consequence |
|---|---|
| Password recovery is not implemented | A user who forgot the password cannot recover it themselves; the only way is for an administrator to set a new password through the user card |
| An expired trash retention period means irreversibility | A deleted attachment cannot be restored; start the cleanup deliberately |
| The project usage counter is updated during cleanup | Between deleting an attachment and cleaning the trash the quota looks occupied, although the file is no longer used by anyone |
| Background cleanup of unattached files is disabled together with the trash auto-cleanup | Such files start accumulating; empty the trash manually |
| The background sync interval cannot be configured through the settings file | The actual interval is 5 minutes; a code change is required |
| Some models require heavy dependencies that are not part of the standard installation | Without the additional installation the image works, but the models are unavailable |
| The system summary is not displayed in the interface | The total number of users, projects, and tasks is available only by a direct request |
