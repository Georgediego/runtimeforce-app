/**
 * Frontend service for model usage metrics.
 */
import { usageApi } from "../core/api_http_client.js";
import { eventBus } from "../core/event_bus.js";

export const usageFrontendService = {
    async fetchSummary(hours = 24) {
        try {
            const data = await usageApi.summary(hours);
            eventBus.emit("usage:summary_updated", data);
            return data;
        } catch (e) {
            console.warn("Failed to fetch usage summary:", e);
            return null;
        }
    }
};
