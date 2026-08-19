/**
 * Frontend service for detecting and selecting local engines (Ollama/LM Studio).
 */
import { modelsApi } from "../core/api_http_client.js";
import { eventBus } from "../core/event_bus.js";

export const localModelsService = {
    async discoverLocalModels() {
        try {
            const data = await modelsApi.list();
            const models = data.models || {};
            const local = [...(models.ollama || []), ...(models.lm_studio || [])];
            eventBus.emit("models:local_discovered", local);
            return local;
        } catch (e) {
            console.warn("Failed to discover local models:", e);
            return [];
        }
    }
};
