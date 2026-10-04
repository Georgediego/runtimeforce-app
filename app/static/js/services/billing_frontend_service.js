/**
 * Frontend service for billing status and credit ledger updates.
 */
import { billingApi } from "../core/api_http_client.js";
import { eventBus } from "../core/event_bus.js";

export const billingFrontendService = {
    async fetchStatus() {
        try {
            const data = await billingApi.status();
            eventBus.emit("billing:status_updated", data);
            return data;
        } catch (e) {
            console.warn("Failed to fetch billing status:", e);
            return null;
        }
    },
    async fetchCredits() {
        try {
            const data = await billingApi.credits();
            eventBus.emit("billing:credits_updated", data);
            return data;
        } catch (e) {
            console.warn("Failed to fetch credits:", e);
            return null;
        }
    }
};
