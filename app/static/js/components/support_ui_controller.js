/**
 * Support Ticket Intake UI Controller.
 */
import { supportFrontendService } from "../services/support_frontend_service.js";
import { showToast } from "./toast_ui_controller.js";

export const supportUIController = {
    async submitTicket(subject, description) {
        try {
            const res = await supportFrontendService.createTicket(subject, description);
            showToast(`Support ticket created: #${res.id}`, "success");
            return res;
        } catch (e) {
            showToast(`Failed to submit ticket: ${e.message}`, "error");
            return null;
        }
    },
    async listTickets() {
        try {
            const data = await supportFrontendService.listTickets();
            return data.tickets || [];
        } catch (e) {
            console.warn("Failed to list support tickets:", e);
            return [];
        }
    }
};
