namespace MCP.Industrial.Api;

/// <summary>
/// Agente de supervisión: combina las herramientas deterministas (solo lectura)
/// con un modelo de OpenRouter cuando hay clave configurada. Si el LLM falla,
/// responde con la lógica de reglas y lo indica en la traza.
/// </summary>
public sealed class AgentService(PlantState plant, OpenRouterAgent llm)
{
    public object Status() => new
    {
        mode = llm.Enabled ? "llm" : "rules",
        enabled = llm.Enabled,
        model = llm.Model,
        models = llm.Modelos.Select(m => new { id = m.Id, nombre = m.Nombre, gratis = m.Gratis }),
        provider = "OpenRouter",
        scope = "solo lectura · sin escritura al PLC",
    };

    public async Task<AgentReply> AskAsync(string? message, CancellationToken token, string? modelo = null)
    {
        var rules = plant.Ask(message);
        if (!llm.Enabled) return rules with { Mode = "rules" };

        var user = (message ?? string.Empty).Trim();
        if (user.Length == 0) user = "Resume el estado actual de la planta.";

        var result = await llm.CompleteAsync(plant.BuildSystemContext(), user, token, modelo);

        var trace = rules.Tools.ToList();
        trace.Add(new AgentCall(
            "consulta_openrouter",
            result.Ok,
            result.Ms,
            result.Ok ? $"modelo {result.Model}" : (result.Error ?? "sin respuesta")));

        if (!result.Ok)
            return rules with { Tools = trace, Mode = "rules", Model = null };

        return new AgentReply(result.Text!, "Agente de supervisión · OpenRouter", DateTimeOffset.Now, trace, "llm", result.Model);
    }
}
