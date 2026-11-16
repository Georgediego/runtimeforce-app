# Workspaces & SSH — Project Isolation

## One project, one workspace context

Workspace configuration belongs to a RuntimeForce project. A project can have its own local folder or its own SSH workspace. Workspace records are scoped by both the local user and the project ID.

When a project is selected, workspace resolution uses that project's workspace record. It must not silently reuse the last active workspace belonging to another project.

## Create a project

New projects are created without an attached workspace, SSH host, inherited local path or preconfigured project context. This is intentional: configure the target only after the project exists.

## Configure a local workspace

1. Open Projects.
2. Open settings for the project you want to configure.
3. Open the Workspace tab.
4. Add a local workspace and select its directory.
5. Test the configuration and activate it for that project.

## Configure an SSH workspace

1. Open settings for the target project.
2. Open the Workspace tab and choose Add SSH Workspace.
3. Enter the host, port, username and authentication method.
4. Select the SSH key or credential required for that host.
5. Test the connection and activate it for that project.

Do not assume that an SSH connection configured for one project is available to another project.

## Switching projects

Switching the active project changes the project context used by the editor, file tree, terminal, agent tools and Git operations. A project without a workspace remains disconnected. It must not fall back to a different project's local folder or SSH host.

## Limits

Project, SSH host and other limits are determined by the active plan's server-verified entitlements. A plan may limit the number of projects or unique SSH hosts.

## Troubleshooting

- If the file tree is empty, verify that the selected project has an active workspace.
- If an SSH connection fails, test the host, port, username and selected key from that project's Workspace settings.
- If a project has no workspace, add one explicitly rather than switching to another project's connection.
