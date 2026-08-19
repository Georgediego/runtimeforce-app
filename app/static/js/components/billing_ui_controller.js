/**
 * Billing & Credits UI Controller.
 */
import { billingFrontendService } from "../services/billing_frontend_service.js";

export const billingUIController = {
    async refreshCredits() {
        return await billingFrontendService.fetchCredits();
    }
};
