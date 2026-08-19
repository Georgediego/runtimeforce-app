/**
 * Usage Statistics UI Controller.
 */
import { usageFrontendService } from "../services/usage_frontend_service.js";

export const usageUIController = {
    async refreshSummary(hours = 24) {
        return await usageFrontendService.fetchSummary(hours);
    }
};
