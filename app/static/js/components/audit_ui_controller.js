/**
 * Local Audit Log UI Controller.
 */
import { auditApi } from "../core/api_http_client.js";

export const auditUIController = {
    async loadLogs(limit = 50) {
        try {
            const data = await auditApi.logs(limit);
            return data.logs || [];
        } catch (e) {
            console.warn("Failed to fetch audit logs:", e);
            return [];
        }
    }
};
