/**
 * Frontend service for Studio Plan project operations.
 */
import { projectsApi } from "../core/api_http_client.js";
import { eventBus } from "../core/event_bus.js";

export const projectFrontendService = {
    async listProjects() {
        const data = await projectsApi.list();
        eventBus.emit("project:list_updated", data);
        return data;
    },
    async bumpVersion(projectId, changelog, bumpType = "patch") {
        const res = await projectsApi.bumpVersion(projectId, changelog, bumpType);
        eventBus.emit("project:version_bumped", res);
        return res;
    }
};
