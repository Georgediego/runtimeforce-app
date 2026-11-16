# Git & GitHub — Project Isolation

## Git configuration belongs to a project

Each project stores its own:

- GitHub repository remote URL
- Main branch preference
- Development branch preference
- Git workflow mode
- Versioning scheme and prerelease tag
- Current project version

The Git working directory is resolved from that project's Workspace / SSH configuration.

## Configure a repository

1. Open Projects.
2. Open settings for the target project.
3. Select the Git tab.
4. Connect your GitHub account if repository discovery requires authorization.
5. Select the repository for this project.
6. Review the remote URL and branch preferences.
7. Save the project settings.

The selected repository remote is stored on the project record. Another project can use a different repository.

## Git operations

Git status, initialization, diff, commit, log, branch listing, push and pull must run against the workspace resolved for the selected project. The local IDE sends the project ID with Git requests; the API validates that the project belongs to the authenticated local user.

Do not rely on a user-global active workspace for Git operations.

## GitHub authorization

GitHub account authorization allows RuntimeForce to discover and access repositories permitted by the connected account. Repository selection and branch/version settings remain project-specific. Disconnecting the account-level GitHub authorization can affect repository discovery or authenticated Git operations for projects that rely on it.

## SSH repositories

A project may use an SSH workspace and a Git remote configured for SSH authentication. When a project remote is stored as a GitHub HTTPS clone URL and the workspace runs over SSH, RuntimeForce converts the project's `origin` remote to the equivalent GitHub SSH URL before initialization, push or pull. The remote host must have an SSH key authorized for that GitHub repository.

## Troubleshooting

- Confirm that the intended project is active before using the main Git panel.
- Confirm that the project's Workspace points to the repository directory.
- Confirm that the project's remote URL and branch preferences are correct.
- For private repositories, verify the GitHub authorization or credentials used by that project.
