# Kipatik User Guide

Kipatik is a web system for managing software development projects. It provides a task board, lets you discuss tasks in comments, keeps a history of changes, and automatically pulls commits and Pull Requests from a Git repository.

This guide is intended for project participants: developers, testers, managers and project managers. It describes the interface as a whole: from signing in to the system to working with the Git integration.

## How to read this guide

Button, field and section names are given in «quotes» exactly as they appear in the interface. Actions are described in short steps.

### Notation

| Notation | Meaning |
|---|---|
| Bar on the left of the card: red, amber, blue | high, medium, low priority |
| Task type badge: «Исправление» (“Fix”), «Новая функциональность» (“New feature”), «Рефакторинг» (“Refactoring”), «Документация» (“Documentation”), «Тестирование» (“Testing”), «Сопровождение» (“Maintenance”) | task type; set manually, and determined by the model for commits |
| «вручную» (“manual”) badge | the link to a commit, branch or Pull Request was confirmed by a person |
| «модель» (“model”) badge | the link was suggested by the model based on the meaning of the changes |
| «авто» (“auto”) badge | the link was found automatically, for example by the task number in the commit text |
| Number next to the «модель» (“model”) or «авто» (“auto”) badge | the system's confidence in the link, in percent |
| ⚠ next to the confidence | the confidence is low, the link should be verified |
| Asterisk `*` next to a field | the field is mandatory by the project rules |
| `+N` next to avatars | there are more participants than the avatars shown |
| `99+` and `9+` in counters | the counter is truncated |
| Percentages next to the model estimates | how confident the system is in the conclusion; this is not a guarantee of accuracy |
| Dimmed commit type badge | the model determined this type with low confidence |

---

## 1. Getting started

### 1.1 Signing in

1. Open the system address in the browser — the «Вход в Kipatik» (“Sign in to Kipatik”) page appears.
2. Enter «Имя пользователя или email» (“Username or email”).
3. Enter «Пароль» (“Password”). The eye icon to the left of the field shows the password in plain text and hides it again.
4. Click «Войти» (“Sign in”).

After signing in, «Главная» (“Home”) opens with the list of your projects. If the session is saved, the next time you open the system you are signed in automatically.

You can sign out with the exit icon on the right of the top bar.

### 1.2 Registering an account

1. On the «Вход в Kipatik» (“Sign in to Kipatik”) page, click «Создать аккаунт» (“Create account”) in the bottom block.
2. Fill in «Полное имя» (“Full name”), «Email» and «Пароль» (“Password”).
3. The password must contain from 8 to 72 characters.
4. Click «Зарегистрироваться» (“Sign up”).

After registration you are signed in automatically. If the account already exists, return to the sign-in page with the «Войти» (“Sign in”) link.

### 1.3 Interface language and text size

Both settings are in the profile.

| Setting | Values | How it is applied |
|---|---|---|
| Interface language | English, «Русский» (“Russian”) | Changes immediately after you select it and is stored in the profile; it is picked up automatically at the next sign-in |
| Text size | from 13 to 20 pixels, 16 by default | The «−», «+» and «Сбросить» (“Reset”) buttons, with a preview next to them; stored in the browser and applies to all sections |

### 1.4 Protected and unprotected sections

| Section | Access |
|---|---|
| «Вход» (“Sign in”), «Создание аккаунта» (“Account creation”) | Without signing in |
| «Главная» (“Home”), project board, task card, profile, history | Only after signing in |
| «Админ. панель» (“Admin panel”) | Only for users with administrator rights |

Breadcrumbs are shown on the left of the top bar: «Kipatik», then «Главная» (“Home”) (or «Админ. панель» (“Admin panel”) for an administrator), then the name of the current project.

---

## 2. Home page

The Home page consists of three panels: «Ваши проекты» (“Your projects”), «Ваши задачи» (“Your tasks”) and «Уведомления» (“Notifications”).

**«Ваши проекты» (“Your projects”)** — cards of all projects you are a participant of. Above the cards there is a search field by name. If there are no projects, the «Добро пожаловать в Kipatik» (“Welcome to Kipatik”) screen is shown with a «Создать первый проект» (“Create first project”) button.

**«Ваши задачи» (“Your tasks”)** — tasks assigned to you, across all projects.

| Element | Purpose |
|---|---|
| Search field above the list | Filter by title and description |
| «Сортировка» (“Sort”) list | «Дедлайн» (“Due date”), «Приоритет» (“Priority”), «Статус» (“Status”), «Новые» (“New”) |
| Task card | Opens the task card in its project |

**«Уведомления» (“Notifications”)** — the full list of notifications. The panel header shows the unread counter; when the count is above 99, “99+” is shown.

**Collapsing panels.** Each panel header has a chevron — «Свернуть панель» (“Collapse panel”) and «Развернуть панель» (“Expand panel”). A collapsed panel turns into a narrow strip. No more than one panel is collapsed at a time: if you collapse another one, the previously collapsed panel expands.

**Changing the width of the projects panel.**

1. Hover the cursor over the vertical divider between the «Ваши проекты» (“Your projects”) and «Ваши задачи» (“Your tasks”) panels.
2. Hold the left mouse button and drag the divider to the right or to the left.
3. Release the button.

The width ranges from 20 to 60 percent of the window and is remembered for this browser.

---

## 3. Projects

### 3.1 Creating a project

The button is available only to users who are allowed to create projects.

1. On the Home page, click the «Создать новый проект» (“Create new project”) tile or the «+» icon in the header of the «Ваши проекты» (“Your projects”) panel.
2. In the «Новый проект» (“New project”) dialog, fill in «Название проекта» (“Project name”).
3. Optionally, fill in «Описание» (“Description”).
4. Click «Создать проект» (“Create project”).

The repository connection wizard opens immediately after creation — see section 6.2.

### 3.2 Project card on the Home page

The card shows the name and description (without a description, «Описание отсутствует» (“No description”) is shown), the owner with the «(Вы)» (“(You)”) mark, your role, the name of the connected repository, up to three participant avatars with «+N» when there are more, and the total participant counter, as well as the provider badge: GitHub, GitLab, Bitbucket or Git. Clicking the card opens the project board.

### 3.3 Participants and invitations

1. Open the project and click «Участники» (“Participants”) in the header.
2. In the «Участники» (“Participants”) dialog there are the tabs «Участники проекта» (“Project participants”) and «Приглашение» (“Invitation”). The «Приглашение» (“Invitation”) tab is available to the «Рук. проекта» (“Project Manager”) and «Менеджер» (“Manager”) roles.

**«Участники проекта» (“Project participants”)** shows the avatar, name and role of each participant, and marks your own row with «(Вы)» (“(You)”). The trash icon on a row removes the participant after confirmation. You cannot remove yourself or the project owner — the button is hidden for them.

**«Приглашение» (“Invitation”)**:

1. Enter a name or email in the search field — at least two characters. Already invited people, active participants and you yourself are not shown in the results.
2. Choose the role of the future participant in the «Роль для приглашения» (“Role for invitation”) list.
3. Click «Пригласить» (“Invite”) next to the found user — the confirmation «Приглашение отправлено пользователю <email>» (“Invitation sent to user <email>”) appears.
4. The «Ожидают принятия» (“Awaiting acceptance”) list shows the sent but not accepted invitations with the status «Ожидание…» (“Pending…”).

The «Рук. проекта» (“Project Manager”) role is available only to those who already have it: a manager cannot assign it. The dialog is closed with the button at the bottom.

### 3.4 Participant roles and what each role can do

There are five roles in a project.

| Capability | «Рук. проекта» (“Project Manager”) | «Менеджер» (“Manager”) | «Разработчик» (“Developer”) | «Тестировщик» (“Tester”) | «Наблюдатель» (“Observer”) |
|---|---|---|---|---|---|
| Viewing the project, the board and tasks | yes | yes | yes | yes | yes |
| Creating tasks | yes | yes | yes | yes | no |
| Editing tasks | yes | yes | only their own tasks | only tasks assigned to them | no |
| Deleting tasks | yes | yes | only their own tasks | no | no |
| Moving tasks between columns | yes | yes | yes | yes | no |
| Assigning an assignee | yes | yes | only on tasks where they are already the assignee | no | no |
| Priority, due dates, subtasks | yes | yes | in their own tasks | in the tasks assigned to them | no |
| Inviting participants and roles | yes | yes | no | no | no |
| Removing a participant from the project | yes | yes, but not a participant with the «Рук. проекта» (“Project Manager”) role | no | no | no |
| Project rules | yes | yes | no | no | no |
| Project settings, Git connection, webhooks | yes | yes | no | no | no |
| Creating a branch from a task | yes | yes | if they are the task assignee | no | no |
| Comments | yes | yes | yes | yes | no |
| Deleting any comment | yes | yes | only their own | only their own | no |
| Pull Request: viewing, commenting, approving | yes | yes | yes | yes | viewing only |
| Deleting the project | only the project owner or an administrator | no | no | no | no |

Additionally: the right to create projects is granted separately and does not depend on the project role; an administrator who is not a participant of the project automatically gets the rights of the «Рук. проекта» (“Project Manager”) role.

### 3.5 Project background

The background is configured in «Настройки проекта» (“Project settings”), the «Общее» (“General”) tab, the «Фон страницы» (“Page background”) section.

| Option | What happens |
|---|---|
| «Без фона» (“No background”) | The background is removed, the page stays white |
| «Базовый» (“Basic”) | The background from the system bundle is applied |
| «Свой» (“Custom”) | A file picker opens; only PNG and JPEG are accepted |

The background is applied immediately, no separate «Сохранить» (“Save”) button is required. A hint warns: the background is visible to all participants of the project, and the same person who changes the project name changes it. «Выбрать файл» (“Choose file”) replaces the background, «Убрать фон» (“Remove background”) deletes it. While the background is being saved, «Сохраняем фон…» (“Saving background…”) is shown, on error — «Не удалось изменить фон» (“Failed to change the background”).

### 3.6 Deleting a project

Only the project owner or an administrator can delete a project.

1. Open «Настройки» (“Settings”) in the project header and go to the «Общее» (“General”) tab.
2. Click «Удалить проект» (“Delete project”).
3. Confirm the deletion in the warning that the action cannot be undone and all tasks and files will be deleted.

For the other participants, instead of the settings a warning is shown: «Только владелец проекта может изменять эти настройки» (“Only the project owner can change these settings”).

---

## 4. Project board

### 4.1 Project header

| Element | Purpose |
|---|---|
| Project name | Click the name or the pencil icon — renaming. Available to the project owner and the administrator |
| «Фильтр» (“Filter”) | Task filter panel; next to it is the number of active filters |
| «Правила проекта» (“Project rules”) | Rules configuration. The button is available to the «Рук. проекта» (“Project Manager”) and «Менеджер» (“Manager”) roles |
| «Участники» (“Participants”) | Participants and invitations dialog |
| «Настройки» (“Settings”) | Project settings dialog: general, Git, unlinked events |
| «Сменить проект» (“Switch project”) | Return to the project list |
| «Новая задача» (“New task”) | Task creation dialog |

When renaming, press Enter to save or Esc to cancel; an empty name cannot be saved. The «Новая задача» (“New task”) button is inactive while the project has no columns at all. Above each group of columns a counter of tasks visible after the filter is shown.

The project rules offer:

- «Обязательные поля при создании» (“Required fields on creation”) — Description, Due date, Assignee, Priority. Such fields are marked with an asterisk in the task creation dialog.
- «Автоматическое назначение исполнителя» (“Automatic assignee assignment”) — when a task is moved to another column, the current user becomes the assignee.
- «Логика даты начала выполнения» (“Start date logic”) — one of the options: «Совпадает с датой создания» (“Matches the creation date”), «Задается руководителем/менеджером» (“Set by the Project Manager/Manager”), «Задается исполнителем» (“Set by the assignee”).
- «Ограничения по колонкам для ролей» (“Column restrictions for roles”) — for each column, the roles that are allowed to move tasks into it are selected.
- «Пользовательские SQL-правила» (“Custom SQL rules”) — a field with a SQL query. «Проверить» (“Check”) shows «Запрос корректен» (“The query is valid”) or «Ошибка в запросе» (“Error in the query”); «Добавить правило» (“Add rule”) appears only after a successful check. Saved rules are listed and can be deleted.

Click «Сохранить» (“Save”) to apply the rules.

### 4.2 Five views

View tabs are located under the project header; the active one is highlighted with a colored line at the bottom.

| Tab | What it shows |
|---|---|
| «Доска» (“Board”) | Kanban with columns and task cards |
| «Список» (“List”) | Task table with sorting and search |
| «Карта» (“Map”) | Timeline: task bars by month |
| «Граф» (“Graph”) | Diagram of dependencies between tasks |
| «История» (“History”) | Project activity feed |

**«Список» (“List”).** The toolbar has a search by title and description. Clicking the «Заголовок» (“Title”), «Статус» (“Status”), «Приоритет» (“Priority”), «Срок выполнения» (“Due date”) column headers toggles sorting between ascending and descending. A row shows the task number, title, description, status, priority, due date, assignee, and the subtask and comment counters. Clicking a row opens the task card.

**«Карта» (“Map”).** The scale shows three months from the selected date, with a day grid and highlighted weekends.

- The ‹ arrow shifts the window one month back, the › arrow — one month forward.
- The button between the arrows returns to the current month.
- Task bars are colored by column group and labeled with the task number on the right; clicking a bar opens the task.
- If no bars are visible, the hint «Установите даты начала или завершения, чтобы увидеть задачи на дорожной карте» (“Set start or finish dates to see tasks on the roadmap”) is shown. Tasks without a separate start date use the creation date.

**«Граф» (“Graph”).** Nodes are tasks, lines are dependencies between them. The node color corresponds to the priority, labels appear when you zoom in.

- «Добавить зависимость» (“Add dependency”) starts link mode: first select the task that will depend on another, then the task it depends on.
- «Отмена» (“Cancel”) in the graph header turns off link mode; clicking a node opens the task card.
- The «Статистика» (“Statistics”) panel shows the number of tasks by priority and in total.

**«История» (“History”).** Project activity feed: tasks and Git events, up to 100 entries. Details — in section 8.

### 4.3 Columns: add, rename, delete

Columns are grouped into three groups: `TODO`, `IN PROGRESS`, `DONE`. Within a group the columns go in order.

**Add:** click the «+» icon in the header of the needed group, enter «Название» (“Name”) in the «Добавить колонку» (“Add column”) dialog, check the hint «Будет добавлена в состояние …» (“It will be added to the state …”) and save.

**Rename:** hover the cursor over the column header, click the pencil icon, change «Название» (“Name”) in the «Изменить колонку» (“Edit column”) dialog and save.

**Delete:** hover the cursor over the column header, click the trash icon and confirm the deletion in the question «Вы уверены, что хотите удалить эту колонку? Задачи останутся в проекте» (“Are you sure you want to delete this column? The tasks will remain in the project”).

### 4.4 Dragging tasks between columns

1. Click the task card and, holding the mouse button, drag it to another column.
2. During the drag, a translucent copy of the card is visible next to the cursor.
3. Release the button — the task immediately gets the status of the new column.

You can also move a card without the mouse: select it with the keyboard and move it with the arrow keys. If «Автоматическое назначение исполнителя» (“Automatic assignee assignment”) is enabled in the project, the current user becomes the assignee when the task is moved.

### 4.5 Task filter

1. Click «Фильтр» (“Filter”) in the project header.
2. Select the conditions in the «Фильтр задач» (“Task filter”) panel:

| Condition | Values |
|---|---|
| «Исполнитель» (“Assignee”) | Project participants and the «Любой» (“Any”) option |
| «Приоритет» (“Priority”) | «Низкий» (“Low”), «Средний» (“Medium”), «Высокий» (“High”) |
| «Тип» (“Type”) | Six task types as colored badges |
| «Просроченные» (“Overdue”) | Only tasks whose due date has passed |

3. The «Показано X из Y» (“Showing X of Y”) row shows how many tasks are left.
4. The «Сбросить» (“Reset”) button clears all conditions.

The filter works the same way in all views — «Доска» (“Board”), «Список» (“List”), «Карта» (“Map”) and «Граф» (“Graph”) — and applies immediately to the already loaded project tasks.

### 4.6 Searching for tasks in the app header

The «Поиск задач...» (“Search tasks...”) field in the top bar searches across all your projects.

1. Enter at least two characters in the «Поиск задач...» (“Search tasks...”) field.
2. The results show the task name and the project name.
3. Click a result — the task card opens in the right project.

Enter opens the first result, Esc and a click outside the field close the results. When there are no results, «Ничего не найдено» (“Nothing found”) is shown, on failure — «Не удалось выполнить поиск» (“Failed to run the search”). The field is hidden on narrow screens.

---

## 5. Tasks

### 5.1 Creating a task

You can create a task with the «Новая задача» (“New task”) button in the project header or with the «+ Добавить задачу» (“+ Add task”) button at the bottom of the needed column — the column will be preselected.

1. Enter «Заголовок» (“Title”) — this is the only field that is always mandatory.
2. If necessary, fill in «Описание» (“Description”), «Дата начала» (“Start date”) and «Срок выполнения» (“Due date”).
3. Select «Тип» (“Type”) and «Приоритет» (“Priority”).
4. If necessary, add subtasks in the «Чек-лист» (“Checklist”).
5. Optionally, click «Анализ ИИ» (“AI analysis”) — see section 7.1.
6. Click «Добавить задачу» (“Add task”).

Fields marked with an asterisk are mandatory by the project rules: if such a field is not filled in, the task is not created and the system reports it. To abort, there is «Отмена» (“Cancel”).

### 5.2 Task fields

| Field | Where it is set |
|---|---|
| «Заголовок» (“Title”) | Creation dialog, then the task card header |
| «Описание» (“Description”) | Creation dialog, «Общее» (“General”) tab |
| «Статус» (“Status”) (column) | Task card sidebar, by dragging on the board |
| «Тип» (“Type”) | Sidebar, creation dialog: «Без типа» (“No type”), «Исправление» (“Fix”), «Новая функциональность» (“New feature”), «Рефакторинг» (“Refactoring”), «Документация» (“Documentation”), «Тестирование» (“Testing”), «Сопровождение» (“Maintenance”) |
| «Приоритет» (“Priority”) | Sidebar, creation dialog: «Низкий» (“Low”), «Средний» (“Medium”), «Высокий» (“High”) |
| «Дата начала» (“Start date”) and «Срок выполнения» (“Due date”) | Sidebar, creation dialog |
| «Исполнитель» (“Assignee”) | Sidebar, creation dialog: «Не назначен» (“Unassigned”) or a project participant |
| «Подзадачи» (“Subtasks”) | «Чек-лист» (“Checklist”) in the creation dialog, checklist in the «Общее» (“General”) tab |
| «Зависимости» (“Dependencies”) | The «Зависимости» (“Dependencies”) section in the «Общее» (“General”) tab, the «Граф» (“Graph”) tab |
| «Комментарии и вложения» (“Comments and attachments”) | «Обсуждение» (“Discussion”) tab |
| «Ветки, коммиты, Pull Request» (“Branches, commits, Pull Request”) | «Разработка» (“Development”) tab |
| «Создано» (“Created”) and «Дата начала» (“Start date”) (historical) | «Общее» (“General”) tab, read-only |

### 5.3 Task card: the «Общее» (“General”) tab

The card opens when you click a card on the board, a row in the list, a bar on the map, a node in the graph, a global search result, or the «Задача #N →» (“Task #N →”) link in the history.

In the card header the title can be edited right in the field — the text is saved when the field loses focus; the ✕ icon closes the card. Tabs: «Общее» (“General”), «Обсуждение» (“Discussion”) (with a comment counter), «Разработка» (“Development”) (with a counter of commits and branches), «История» (“History”).

In the «Общее» (“General”) tab «Описание» (“Description”) is edited — in the same way, on focus loss; below it «Создано» (“Created”) and «Дата начала» (“Start date”) are shown read-only, then the subtask checklist with the counter «выполнено X из Y» (“done X of Y”).

The sidebar is available in all tabs:

| Field | How to change it |
|---|---|
| «Статус» (“Status”) | Select a column from the dropdown |
| «Тип» (“Type”) | Click the needed type; the selected one has a checkmark |
| «Приоритет» (“Priority”) | Click «Низкий» (“Low”), «Средний» (“Medium”) or «Высокий» (“High”) |
| «Дата начала» (“Start date”), «Срок выполнения» (“Due date”) | Specify the date and time |
| «Исполнитель» (“Assignee”) | Select «Не назначен» (“Unassigned”) or a project participant |

When a task is assigned to another person, they receive a notification.

### 5.4 Subtasks

**Add:** the «Общее» (“General”) tab → the «Добавить подзадачу...» (“Add subtask...”) field → the «+» button.

**Mark as done:** put a checkmark in the checkbox next to the subtask. The «выполнено X из Y» (“done X of Y”) counter and the progress bar are updated; a subtask progress bar appears on the task card on the board.

**Delete:** hover the cursor over the subtask row and click the trash icon.

When a task is being created, subtasks are added in the «Чек-лист» (“Checklist”) of the creation dialog, where the trash icon removes a row before the task is created.

### 5.5 Dependencies between tasks

**Add:** the «Общее» (“General”) tab → the «Зависимости» (“Dependencies”) section → «Добавить зависимость» (“Add dependency”) → enter the task name or its number with a hash sign, for example `#42` → select the found task.

**Delete:** hover the cursor over the dependency row and click the trash icon.

If there are no dependencies, «Зависимости не указаны» (“No dependencies specified”) is shown. Dependencies are visible on the «Граф» (“Graph”) tab as a line between tasks; there they can be added by first selecting the dependent task, then the task it depends on.

### 5.6 The «Обсуждение» (“Discussion”) tab

**Comment.** Enter the text in the field at the bottom, attach files if necessary and click «Комментировать» (“Comment”). Comments are refreshed automatically every five seconds while the tab is open, and the feed scrolls by itself to the last message.

**Reply to a comment.**

1. Hover the cursor over a comment and click «Ответить» (“Reply”).
2. A quote with the author name and the beginning of the text appears in the input field.
3. Write your reply and click «Комментировать» (“Comment”). The ✕ icon in the quote block cancels the reply.

**Reactions.** Hover the cursor over a comment, click the emoji icon and select a reaction: 👍 ✅ 👀 🚀 ❤️ 🔥 😂 😮. Reactions are shown under the comment with counters, your own ones are highlighted; selecting the same reaction again removes it.

**Attachments.** The paperclip icon in the input field uploads a file; ✕ on a chip removes an unsent attachment; clicking a chip in a published comment downloads the file; ✕ on a chip in the edit form removes the attachment while editing.

Limitations: no more than 5 files in one message; a file larger than 25 MB is rejected on the client with the message «Файл слишком большой (макс. 25МБ)» (“File is too large (max. 25MB)”); the server additionally checks the size, the extension and the project storage limit — see section 11.

**Editing and deleting.** The «⋯» menu on a comment opens «Редактировать» (“Edit”) and «Удалить» (“Delete”). When editing, attachments can be removed at the same time. A comment can be deleted by its author or by a user with the «Рук. проекта» (“Project Manager”) or «Менеджер» (“Manager”) role.

**Text formatting.** Code block — triple backticks; inline code — single backticks; **bold** — two asterisks; *italic* — one; ***both*** — three; link — `[текст](адрес)`; mention — `@` and a name or email without spaces; commit link — `#commit ` and a short identifier, displayed as a badge.

Mentions are entered manually: the hint with the employee list does not appear. The mentioned person receives a notification.

### 5.7 The «Разработка» (“Development”) tab

**Tab header:** the name of the connected repository and the connection state (if the integration is not configured — «Git-интеграция не настроена» (“Git integration is not configured”)), a repository selection if there are several, the «Обновить» (“Refresh”) button and the «Создать ветку» (“Create branch”) button.

«Создать ветку» (“Create branch”) creates a branch `feature/task-<номер задачи>-<фрагмент заголовка>` in the repository and automatically moves the task to the `IN PROGRESS` group. The button is available to the «Рук. проекта» (“Project Manager”), «Менеджер» (“Manager”) roles and to the task assignee.

**The «Прогресс» (“Progress”) block** is first; details — in section 7.2. If there are no commits, «Оценка пока невозможна: к задаче не привязан ни один коммит» (“The estimate is not possible yet: not a single commit is linked to the task”) is shown.

**The «Предложения (N)» (“Suggestions (N)”) section** — suggestions of the tracing model, see section 7.4; each one has «Принять» (“Accept”) and «Скрыть» (“Hide”).

**The «Ветка» (“Branch”) section** — a list of branches with the link source badge: «вручную» (“manual”), «модель» (“model”) or «авто» (“auto”).

**The «Pull Request» section** — for each request the number and the name with a link to the provider are shown, the status (open, merged, closed), the source branches and assignees, the summary `+N −M`, the number of changed files, the state of the CI checks («CI пройден» (“CI passed”), «CI упал» (“CI failed”), «CI выполняется» (“CI running”)) with a link to the run, and a list of reviewers with their decisions; those who have not responded yet are marked «ждём» (“waiting”).

**The «Отклонённые (N)» (“Rejected (N)”) section** — a collapsed list of rejected links, see section 6.8.

**The «Коммиты (N)» (“Commits (N)”) section** — a list with a short identifier, the text, the `+N −M` summary, a commit type badge with a confidence percentage and a link source badge. Expand a commit row to see the full text, the author, the date, a link to the commit at the provider, the mark «Подтверждено пользователем <имя>» (“Confirmed by user <name>”), the line «Тип по смыслу изменений: <тип> · N%» (“Type by the meaning of the changes: <type> · N%”) (and the «тип неуверенный» (“type uncertain”) mark if the type is unreliable) and the list of changed files with icons: added, deleted, renamed, modified; a `+N/−M` summary and, for renamed files, «← предыдущий путь» (“← previous path”).

**The «Изменённые файлы (N)» (“Changed files (N)”) section** — a collapsed list of all files affected by the task.

**Linking and unlinking.** «Перепривязать» (“Relink”) opens the «Привязать объект к задаче» (“Link object to task”) dialog, where every commit or Pull Request has a «Привязать» (“Link”) button. The «🔗×» icon on a commit, branch or Pull Request row unlinks the object after the confirmation «Отвязать этот объект от задачи?» (“Unlink this object from the task?”). If nothing is linked, «С этой задачей пока не связано ни ветки, ни PR, ни коммитов» (“No branch, no PR and no commits are linked to this task yet”) is shown along with the «Перепривязать» (“Relink”) button.

### 5.8 The «История» (“History”) tab of a task

It shows a single feed: the events of the task itself and the Git objects linked to it — branches, commits, Pull Requests. The filters and the grouping by day are the same as in the project history: participant, event type, «Только Git-события» (“Git events only”), «Сбросить фильтры» (“Reset filters”), the marks «Сегодня» (“Today”) and «Вчера» (“Yesterday”).

### 5.9 Deleting a task

1. Open the task card.
2. In the sidebar click «Удалить задачу» (“Delete task”).
3. Confirm the deletion in the question «Вы уверены, что хотите удалить эту задачу?» (“Are you sure you want to delete this task?”).

The card will close, the task will disappear from the project views, and the event will appear in the history.

---

## 6. Working with Git

### 6.1 Connecting a provider account

The provider account is connected in the profile, in the right column «Привязанные аккаунты» (“Linked accounts”). GitHub, GitLab, Bitbucket and Gitea are supported.

**Signing in through the provider**

1. Open the profile and in the block of the needed provider click «Войти через <провайдер>» (“Sign in via <provider>”).
2. Confirm access on the provider page.
3. Return to the system — the account will be linked.

The button appears only if an OAuth application is configured on the server; on refusal, an expired link or a provider mismatch, the system reports the reason.

**Pasting a token**

1. Click «Вставить токен» (“Paste token”) in the provider block.
2. For GitHub enter the username and the token, for the other providers — only the token.
3. Save.

| Provider | What is needed |
|---|---|
| GitHub | Personal Access Token (classic) with the `repo` and `workflow` permissions |
| GitLab | Personal Access Token with the `api` and `read_repository` permissions |
| Bitbucket | App Password with repository access |
| Gitea | Access Token in the Gitea settings |

**Disconnect:** in the block of the connected provider click «Отключить» (“Disconnect”) and confirm the action.

### 6.2 Connecting a repository to a project

The connection wizard consists of three steps.

**Step 1 — Provider**

1. Select the provider: GitHub, GitLab, GitLab (self-hosted), Gitea or Bitbucket.
2. For self-hosted, specify «Адрес сервера (self-hosted)» (“Server address (self-hosted)”).
3. Specify «Токен доступа» (“Access token”). If the account is already connected in the profile, the field is optional — the token will be filled in automatically.
4. Click «Проверить» (“Check”): on success «Токен рабочий. Аккаунт: <имя>» (“The token works. Account: <name>”) is shown.
5. Click «Далее» (“Next”).

**Step 2 — Repository**

1. Enter «URL репозитория» (“Repository URL”).
2. Specify «Ветка по умолчанию» (“Default branch”) — `main` by default.
3. If necessary, fill in «Фильтр по путям» (“Path filter”) — for monorepositories, list the path prefixes separated by commas; an empty field means that the repository is not filtered.
4. Click «Подключить» (“Connect”).

**Step 3 — Webhook**

The wizard shows the checklist «Секрет подписи сгенерирован» (“The signing secret is generated”) and «Вебхук зарегистрирован у провайдера» (“The webhook is registered with the provider”). If the registration succeeded, the «Интеграция готова» (“Integration ready”) badge appears. Details — in section 6.5. The «Готово» (“Done”) button closes the wizard.

### 6.3 Several repositories in one project

1. Open «Настройки» (“Settings”) → the «Git» tab.
2. Click «Добавить ещё репозиторий» (“Add another repository”) and go through the wizard.

In the «Подключённые репозитории» (“Connected repositories”) list select the active repository — the one whose data is shown by default; next to it there is a sync error or success indicator. If there are several repositories, the needed one is also selected on the «Разработка» (“Development”) tab of the task card.

### 6.4 Synchronization and connection check

**Synchronization**

1. Open «Настройки» (“Settings”) → the «Git» tab and click «Синхронизировать» (“Synchronize”).

The «Синхронизация» (“Synchronization”) block shows the default branch, the time of the last synchronization (“never”, if there has not been one yet), the state («Успешно» (“Success”), «Ошибка» (“Error”), «Не выполнялась» (“Not run”)) and the parsing state («Идёт разбор» (“Parsing”), «Готово» (“Done”), «Ошибка разбора» (“Parsing error”), «Не выполнялся» (“Not run”)). If parsing has not finished, a message about the loaded commits and about the fact that parsing continues is shown; suggestions will appear in task cards later — refresh the «Разработка» (“Development”) tab. Besides the manual one, the system periodically refreshes the connected repositories on its own.

**Connection check**

1. In the same block click the «↻» check icon.

The result is four marks: «Репозиторий найден» (“Repository found”) (the system sees the repository at the provider), «Секрет подписи настроен» (“The signing secret is configured”) (the secret matches the settings on the provider side), «Тестовое событие получено» (“Test event received”) (events really do arrive), «Подпись верифицирована» (“Signature verified”) (the signature of the last event is correct). In addition, the time of the last event and the time of the last verified signature are shown.

### 6.5 Webhooks

A webhook is the mechanism through which the provider reports new commits and Pull Requests to the system.

**Automatic registration.** If the provider supports it, on step 3 of the wizard the «Зарегистрировать автоматически» (“Register automatically”) button is available, and after success — the «Интеграция готова» (“Integration ready”) badge.

**Manual setup.** For providers without automatic registration the warning «Этот провайдер не поддерживает авторегистрацию» (“This provider does not support automatic registration”) is shown.

1. Copy «URL вебхука» (“Webhook URL”) and «Секрет» (“Secret”) with the «Скопировать» (“Copy”) buttons.
2. In the Webhooks settings of your repository at the provider add a webhook with this data.
3. Follow the hint «События: push, pull request (merge request)» (“Events: push, pull request (merge request)”).

The URL and the copy button are also in «Настройки» (“Settings”) → «Git», where the «Перевыпустить секрет» (“Re-issue the secret”) button is available as well — after re-issuing, the secret has to be updated at the provider.

### 6.6 Matching commit authors

To display the commit author in tasks and history, match them with a system user.

1. Open «Настройки» (“Settings”) → the «Git» tab.
2. Click «Сопоставить авторов коммитов» (“Match commit authors”).

| Dialog element | Purpose |
|---|---|
| «Атрибуция коммитов» (“Commit attribution”) with a progress bar | How many commits are matched: “X / Y (Z%)” |
| Counters «Авторов» (“Authors”), «Не опознано» (“Unidentified”), «Автоматом» (“Automatically”) | The overall picture for the repository |
| Filters «Все» (“All”), «Не опознанные» (“Unidentified”), «Сопоставленные» (“Matched”) | Limit the author list |
| Author search field | Filter the list |
| «Пересопоставить» (“Rematch”) | Automatic matching once again |
| «Обновить» (“Refresh”) | Reload the list |
| «Сопоставить ▾» (“Match ▾”) next to an author | Manual selection of a user from the candidates |

Commits are matched by email first, then by the provider login. If a developer uses a personal email or another login, set the mapping manually; a matched author is shown with the «авто» (“auto”) or «сохранено» (“saved”) badge. If there are no authors, «Авторов не найдено. Выполните синхронизацию репозитория» (“No authors found. Synchronize the repository”) is shown. While some commits are not matched, a warning stays at the top of the dialog saying that their authorship will not be displayed in tasks and history.

### 6.7 How a commit ends up in a task

There are three ways, and you can use them at the same time.

| Way | How it works | What the user does |
|---|---|---|
| Automatically by number | If the commit text contains a reference like `#15`, the commit is linked to task №15 | Put the task number in the commit text |
| By meaning, by the model | The model matches the meaning of the commit changes with the task texts and suggests a link | Open «Предложения» (“Suggestions”) on the «Разработка» (“Development”) tab and decide: «Принять» (“Accept”) or «Скрыть» (“Hide”) |
| Manually | Linking any commit or Pull Request from the «Привязать объект к задаче» (“Link object to task”) dialog, and also from «Непривязанные события» (“Unlinked events”) | Open «Перепривязать» (“Relink”) or the «Непривязанные события» (“Unlinked events”) tab |

Every linked object shows the source badge: «вручную» (“manual”), «модель» (“model”) or «авто» (“auto”).

### 6.8 Rejected links and returning them for review

1. Open the «Разработка» (“Development”) tab and expand the «Отклонённые (N)» (“Rejected (N)”) section — the short identifier and the commit text are visible there.
2. Click «Вернуть» (“Return”) next to the needed link. The message «Предложение возвращено к рассмотрению» (“The suggestion was returned for review”) appears, and the suggestion will end up in the «Предложения» (“Suggestions”) section again.

### 6.9 Creating a branch from a task

1. Open the task card and go to the «Разработка» (“Development”) tab.
2. Click «Создать ветку» (“Create branch”).

A branch `feature/task-<номер задачи>-<фрагмент заголовка>` will be created, and the task will automatically move to the `IN PROGRESS` group. The button is available to the «Рук. проекта» (“Project Manager”), «Менеджер» (“Manager”) roles and to the task assignee.

### 6.10 Unlinked events

1. Open «Настройки» (“Settings”) → the «Непривязанные события» (“Unlinked events”) tab; the tab header shows a counter.
2. For each event the type (`push` or `pull_request`), the short identifier, the time and the commit text or the Pull Request name are specified.
3. Enter the task number in the `Task #ID` field and click “Link”.

If there are no unlinked events, “All Git events are linked!” is shown.

---

## 7. Automatic analysis (AI)

### 7.1 Task analysis on creation

1. Open the task creation dialog.
2. Fill in «Заголовок» (“Title”) and, if possible, «Описание» (“Description”).
3. Click «Анализ ИИ» (“AI analysis”). The button is active only if the title is filled in; during the analysis it shows «Анализирую...» (“Analyzing...”).
4. The system will produce a recommendation: the badge «Рекомендуемый приоритет: Высокий» (“Recommended priority: High”) or «Рекомендуемый приоритет: Обычный» (“Recommended priority: Normal”).
5. Check the result: the priority is already filled in in the form, select a different one manually if necessary.

The recommendation does not cancel the project rules: if the priority is marked with an asterisk and is not filled in, the task still will not be created.

### 7.2 Progress estimate

The «Прогресс» (“Progress”) block is first on the «Разработка» (“Development”) tab of the task card and appears when at least one commit is linked to the task.

| Element | Content |
|---|---|
| Progress bar and percentage | Calculated estimate of readiness |
| Confidence label | «уверенность высокая» (“confidence high”), «уверенность средняя» (“confidence medium”) or «уверенность низкая» (“confidence low”) |
| «Почему такой процент?» (“Why this percentage?”) | Subtasks (X/Y), Volume (changed lines out of the expected ones), Focus (how many of the files named in the description are affected) |
| «Что ограничивает точность» (“What limits the accuracy”) | Reasons: no linked commits, no subtasks, no files mentioned in the description, too little data for calibration |
| Explanation of the source of the expected volume | Where the number of lines comes from: by project, by system or a default value |
| «Динамика по дням» (“Dynamics by day”) | A chart of the volume accumulation by day |

If there has been no activity with commits for at least four days, «Нет коммитов уже N дн.» (“There have been no commits for N days”) appears. If there are no commits at all, «Оценка пока невозможна: к задаче не привязан ни один коммит» (“The estimate is not possible yet: not a single commit is linked to the task”) is shown.

### 7.3 Determining the commit type

The commit type is determined by the meaning of the changes and is shown as a badge in the commit list.

| What you see | How to read it |
|---|---|
| Type badge with a percentage | The type was determined by the model; the confidence in percent is shown next to it |
| Dimmed badge | The model determines this class unreliably on examples — do not rely on it |
| «тип неуверенный» (“type uncertain”) mark | Duplicates the warning about an unreliable class |
| «Тип определён моделью и проверен на примерах» (“The type was determined by the model and verified on examples”) | The class is determined consistently in the check sample |

With an unreliable determination the explanation «Тип определён моделью, но этот класс на примерах определяется ненадёжно» (“The type was determined by the model, but this class is determined unreliably on examples”) appears next to it.

### 7.4 Link suggestions “commit → task”

1. Open the «Разработка» (“Development”) tab of the task card and the «Предложения (N)» (“Suggestions (N)”) section.
2. Each suggestion shows the short commit identifier, the commit text, the confidence in percent and the label «Возможно, относится к задаче: <название>» (“It may relate to the task: <title>”).
3. Click «Принять» (“Accept”) — the link becomes permanent and «Связь подтверждена» (“Link confirmed”) appears.
4. Click «Скрыть» (“Hide”) — the suggestion goes to «Отклонённые» (“Rejected”) and «Предложение скрыто» (“Suggestion hidden”) appears.

Suggestions appear after the repository is synchronized and are updated on the next synchronizations.

### 7.5 What remains to the person

| The model does | The person decides |
|---|---|
| Matches the meaning of the commit changes with the task texts and suggests a link | Whether to accept or hide each suggestion |
| Determines the commit type by the meaning of the changes | Whether this type is correct, especially with a dimmed badge |
| Recommends a priority when a task is created | Whether to keep the recommended priority or to set your own |
| Calculates the progress percentage from the subtasks, the volume and the focus | Whether the estimate reflects the real state of the work |

The rules for working with automatic conclusions:

1. Every conclusion has a confidence in percent. A low confidence is a signal to verify the result manually.
2. With an uncertain type the type badge is dimmed and the «тип неуверенный» (“type uncertain”) mark appears next to it.
3. The model only suggests: no link, no type and no estimate are applied to the task without a decision of a person.
4. The accuracy of the conclusions is not guaranteed: the confidence percentages are an indicator, not an assessment of the quality of your work.

---

## 8. History and activity

The feed is available in two places: the «История» (“History”) tab on the project board and the «История» (“History”) tab in the task card. In the card, Git objects linked to the events are added — branches, commits and Pull Requests.

**What goes into the feed**

| Type group | Events |
|---|---|
| «Создание» (“Creation”) | Task created |
| «Статус» (“Status”) | Status changed: <from> → <to> |
| «Исполнитель» (“Assignee”) | Assignee changed: <from> → <to> |
| «Приоритет» (“Priority”) | Priority changed: <from> → <to> |
| «Комментарии» (“Comments”) | Comment added |
| «Подзадачи» (“Subtasks”) | Subtask added, marked as done or not done, deleted |
| «Вложения» (“Attachments”) | File uploaded, file deleted |
| «Git» | Push to the repository, Pull Request, branch creation and deletion, Git event |

**Feed filters**

| Filter | Values |
|---|---|
| «Участник» (“Participant”) | All participants or a specific participant |
| «Тип» (“Type”) | All types or one of the groups: «Создание» (“Creation”), «Статус» (“Status”), «Исполнитель» (“Assignee”), «Приоритет» (“Priority”), «Комментарии» (“Comments”), «Подзадачи» (“Subtasks”), «Вложения» (“Attachments”), «Git» |
| «Только Git-события» (“Git events only”) | Only events of the Git type |
| «Сбросить фильтры» (“Reset filters”) | Clears all conditions |

The «Показано X из Y» (“Showing X of Y”) row shows the number of filtered events; if nothing matches the conditions, «По выбранным фильтрам ничего не найдено» (“Nothing was found for the selected filters”) is shown.

**Reading the feed.** Events are grouped by day with the marks «Сегодня» (“Today”), «Вчера» (“Yesterday”) and the date. An event with the link «Задача #N →» (“Task #N →”) opens the task card. Inside a push-to-the-repository event the commits are expanded: the first three are shown, the rest — under the label «и ещё N» (“and N more”). The «↻» icon next to the heading refreshes the feed. The project feed shows up to 100 of the latest events.

---

## 9. Profile

Open the profile by clicking the block with the name, email and avatar in the right part of the top bar.

**Left column — main data.** The name is changed in the «Имя» (“Name”) field, the address — in «Email» (“Email”). The avatar is uploaded with the camera icon or is set by the image address in the «URL аватара» (“Avatar URL”) field. For the photo: no more than 5 MB, PNG, JPEG, GIF, WebP formats; the «Убрать фотографию» (“Remove photo”) button deletes it. The result is visible at the top of the form: «Профиль успешно обновлен!» (“The profile has been successfully updated!”), «Файл больше 5 МБ…» (“The file is larger than 5 MB…”), «Не удалось загрузить фотографию» (“Failed to upload the photo”), «Не удалось убрать фотографию» (“Failed to remove the photo”).

**Display settings.** «Язык интерфейса» (“Interface language”) — English or «Русский» (“Russian”), applies immediately and is stored in the profile. «Размер текста» (“Text size”) — the «−», «+», «Сбросить» (“Reset”) buttons, a preview, a range of 13–20 pixels.

**«Привязанные аккаунты» (“Linked accounts”)** — GitHub, GitLab, Bitbucket, Gitea, see section 6.1.

At the bottom of the left column there is a hint with a shield icon: «Ваш email используется для связи коммитов и уведомлений» (“Your email is used to link commits and notifications”). Precisely by the email and the login the system matches commit authors with users. Click «Сохранить» (“Save”) to apply the changes.

---

## 10. Notifications

The bell icon to the right of the search shows the number of unread notifications; when the count is above 9, “9+” is shown.

1. Click the bell — a list of the latest seven notifications opens.
2. «Прочитать все» (“Mark all as read”) marks the whole list as read.
3. «Показать все» (“Show all”) opens the «Уведомления» (“Notifications”) panel on the Home page.
4. Clicking a notification or the button under it marks it as read.

Notifications appear without a page reload; if the browser has allowed system notifications, you also get an OS message. Next to each notification a relative time is shown, for example “2 minutes ago”.

**What comes in notifications**

| Event | What you see |
|---|---|
| Invitation to a project | «Приглашение в проект» (“Project invitation”) and the role you were invited with |
| Your invitation was accepted | «Приглашение принято» (“Invitation accepted”) for the inviter |
| Your invitation was declined | «Приглашение отклонено» (“Invitation declined”) for the inviter |
| You were assigned as an assignee | «Вы были назначены исполнителем задачи: <название>» (“You were assigned as the task assignee: <title>”) |
| You were mentioned in a comment | «<автор> упомянул вас в задаче #<номер>» (“<author> mentioned you in task #<number>”) |

The symbol to the left of the text depends on the type: invitation, task assignment, mention or an information message.

**Invitation to a project.** Open the bell or the «Уведомления» (“Notifications”) panel on the Home page and click «Принять» (“Accept”) — you become a participant of the project, or «Отклонить» (“Decline”) — the inviter receives a notification. The buttons are shown only for unread invitations.

There are no separate notification settings in the system: you cannot disable certain types or specify a delivery address.

---

## 11. Storage administration and limits (what the user sees)

Storage means the files uploaded to the system: comment attachments, profile photos and project backgrounds. Limits are set by the administrator; below is what concerns you as a user.

**Uploading a file in a comment.** More than 5 files in one message is rejected with the message «Максимум 5 файлов в одном сообщении» (“Maximum 5 files in one message”). A file larger than 25 MB is skipped with the message «Файл слишком большой (макс. 25МБ)» (“File is too large (max. 25MB)”). An invalid extension and exceeding the project storage limit are rejected by the server with an error message. By default the server accepts the extensions `.png`, `.jpg`, `.jpeg`, `.gif`, `.pdf`, `.doc`, `.docx`, `.txt`, `.zip`, `.log`; the administrator can change the list.

**Project limit.** Each project has its own storage volume, and if an individual limit is not set, the general one applies; by default the general limit is 500 MB per project. When the limit is exhausted, new files stop uploading, but tasks, comments and the Git integration keep working.

**Why a deleted file is still counted in the trash.** Deleting an attachment does not erase the file from disk: the record goes to the trash, and the space is freed only after it is emptied. The default retention period in the trash is 7 days, automatic cleanup is enabled and runs on a schedule. Practical conclusion: after deleting large attachments the project volume stays the same for a while; if the limit is not enough right away, report it to the administrator — they can empty the trash forcibly.

**Project background and profile photo.** The project background — only PNG and JPEG, the size is limited by the general file limit. The profile photo — no more than 5 MB, PNG, JPEG, GIF, WebP formats.

---

## 12. Known limitations of the current build

Below is what is stated in the interface of the current version but does not work or works only partially. These are build limitations, not instructions.

| Limitation | What happens now | What to do |
|---|---|---|
| Changing a participant role | In the «Участники» (“Participants”) dialog there is a role selection, but the change is not saved | Contact the project administrator |
| «Взять задачу» (“Take the task”) yourself | In the task card there is no button to assign yourself as the assignee | Ask the lead or the manager to assign you |
| The «Фильтр» (“Filter”) button in the «Список» (“List”) view | The button is drawn, but does nothing | Use «Фильтр» (“Filter”) in the project header — it works for the list too |
| Hints when mentioning `@` | The candidate list does not appear | Enter `@` manually: an email or a name without spaces |
| «Забыли пароль?» (“Forgot your password?”) | The link on the sign-in page leads nowhere | Contact the administrator to reset the password |
| Return to the project list | The «На главную» (“Home”) button on the «Проект не выбран» (“No project selected”) screen and the return after deleting a project lead somewhere else than expected | Open the project list with the «Главная» (“Home”) link in the top bar |
| Recommendations of the «Анализ ИИ» (“AI analysis”) | Only the priority is filled in; the task type and subtasks are not | Set the type and the subtasks manually |
| Labels and tags | There are neither labels nor tags in tasks | Use the task type, the subtasks and the filter by type |
| Start date filter and assignee on the map | There is no such filter; tasks without a start date use the creation date, the assignee is not shown on the map | Look at the dates and the assignee in the «Общее» (“General”) tab or in the «Список» (“List”) view |
| Parsing after synchronization | The parsing can take a long time, and its result is visible only after a page refresh | Wait for the «Готово» (“Done”) status and click «Обновить» (“Refresh”) on the «Разработка» (“Development”) tab |
| Notifications about a Pull Request review request | Such notifications are not created | Follow the task and the history feed |

---

## 13. Frequently asked questions

### I forgot my password, what do I do?

There is no password recovery in the system: the «Забыли пароль?» (“Forgot your password?”) link on the sign-in page does not work. Contact the administrator — they will set a new password.

### Where did my commit go?

1. Open «Настройки» (“Settings”) → «Git» → «Проверка подключения» (“Connection check”). If there is no «Тестовое событие получено» (“Test event received”) mark, events from the provider are not arriving.
2. Click «Синхронизировать» (“Synchronize”) and wait for the «Готово» (“Done”) status.
3. Open the «Непривязанные события» (“Unlinked events”) tab — the commit may be there.
4. Check the «Разработка» (“Development”) tab of the needed task, the «Отклонённые» (“Rejected”) section — the suggestion may have been hidden earlier.
5. Make sure the commit text contains a task number like `#15`, if the commit is supposed to be linked automatically.

### Why does the task have no progress estimate?

The estimate appears only when at least one commit is linked to the task. The message «Оценка пока невозможна: к задаче не привязан ни один коммит» (“The estimate is not possible yet: not a single commit is linked to the task”) means exactly that. Link the commits on the «Разработка» (“Development”) tab.

### The model suggested linking the wrong commit

Click «Скрыть» (“Hide”) in the «Предложения» (“Suggestions”) section — the link will go to «Отклонённые» (“Rejected”) and will no longer be suggested. Check the confidence percentage and whether the changes in the commit really relate to the task.

### How do I restore a hidden suggestion?

Open «Разработка» (“Development”) → the «Отклонённые (N)» (“Rejected (N)”) section → «Вернуть» (“Return”). The suggestion will return to «Предложения» (“Suggestions”).

### Why does the filter show nothing?

The «Показано X из Y» (“Showing X of Y”) row in the filter panel shows the result. Common causes: tasks are hidden by a combination of conditions, for example «Просроченные» (“Overdue”) and a specific assignee; the project has no tasks with the selected type; tasks are not loaded — the filter works on the already loaded data. Click «Сбросить» (“Reset”) and check the counter.

### How do I rename a project?

Click the project name in the board header or the pencil icon, enter a new name and press Enter or the save button. Renaming is available to the project owner and the administrator.

### How do I go to another project?

Click «Сменить проект» (“Switch project”) in the header — the Home page with the project list opens. The «Главная» (“Home”) link in the breadcrumbs of the top bar and clicking the «Kipatik» logo work as well.

### Where did the deleted attachment go?

The file goes to the trash and is counted in the project volume until it is emptied. By default the trash is emptied automatically after 7 days. If the space has to be freed urgently, contact the administrator.

### Who can delete a project?

Only the project owner and the administrator. The «Менеджер» (“Manager”) role cannot delete a project.

### Why is the «Новая задача» (“New task”) button not clickable?

The project has not a single column. Add a column with the «+» icon in the header of one of the groups: `TODO`, `IN PROGRESS` or `DONE`.

### How do I change the language or the font size?

Open the profile by clicking your name in the top bar. In the «Ваш профиль» (“Your profile”) section select «Язык интерфейса» (“Interface language”) or change «Размер текста» (“Text size”) with the «−» and «+» buttons. The changes apply immediately.
