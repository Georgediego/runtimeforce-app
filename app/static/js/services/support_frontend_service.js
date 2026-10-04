/**
 * Frontend service for support ticket creation and list.
 */
import { supportApi } from "../core/api_http_client.js";
import { eventBus } from "../core/event_bus.js";

export const supportFrontendService = {
    async createTicket(subject, description, diagnostics = null) {
        const res = await supportApi.createTicket(subject, description, diagnostics);
        eventBus.emit("support:ticket_created", res);
        return res;
    },
    async listTickets() {
        const data = await supportApi.listTickets();
        eventBus.emit("support:tickets_updated", data);
        return data;
    }
};
