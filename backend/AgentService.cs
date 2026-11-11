namespace MCP.Industrial.Api;

/// <summary>
/// Agente de supervisión: combina las herramientas deterministas (solo lectura)
/// con un modelo de OpenRouter cuando hay clave configurada. Si el LLM falla,
/// responde con la lógica de reglas y lo indica en la traza.
/// </summary>
public sealed class AgentService(PlantState plant, OpenRouterAgent llm, ContextoAgente contexto)
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

    private const string Reglas = """
Cómo responder:
- Responde DIRECTO a lo que se pregunta, en español y en 1 a 5 frases (más solo si piden detalle). Empieza por la respuesta, no por el contexto.
- Usa las señales en vivo de abajo; si una pregunta depende de una señal que no aparece o el módulo está SIN COMUNICACIÓN, dilo claramente en una frase. No añadas descargos innecesarios ("los datos no indican...") cuando el dato sí está.
- Interpreta las señales con su significado (p. ej. estado/selector_remoto = 1 → modo REMOTO). Si la señal está marcada [H], menciona que es una hipótesis.
- Usa la conversación previa para entender preguntas cortas ("¿y ahora?", "¿y el de caudal?").
- Nunca digas que ejecutaste una orden: eres de solo lectura; las órdenes se dan desde el SCADA con confirmación.
""";

    public async Task<AgentReply> AskAsync(string? message, CancellationToken token, string? modelo = null, IReadOnlyList<TurnoChat>? historial = null)
    {
        var rules = plant.Ask(message);
        if (!llm.Enabled) return rules with { Mode = "rules" };

        var user = (message ?? string.Empty).Trim();
        if (user.Length == 0) user = "Resume el estado actual de la planta.";

        var sistema = plant.BuildSystemContext() + "\n" + Reglas + "\n" + contexto.Construir();
        var result = await llm.CompleteAsync(sistema, user, token, modelo, historial);

        var trace = rules.Tools.ToList();
        trace.Add(new AgentCall(
            "consulta_openrouter",
            result.Ok,
            result.Ms,
            result.Ok ? $"modelo {result.Model}" : (result.Error ?? "sin respuesta")));

        if (!result.Ok)
            // Se AVISA que la IA no respondio (limite diario, modelo caido...) y por que;
            // la respuesta que sigue es la de reglas deterministas, no la del modelo.
            return rules with
            {
                Reply = $"⚠️ La IA no respondió ({result.Error ?? "sin respuesta"}). Respuesta automática por reglas:\n{rules.Reply}",
                Tools = trace, Mode = "rules", Model = null,
            };

        return new AgentReply(result.Text!, "Agente de supervisión · OpenRouter", DateTimeOffset.Now, trace, "llm", result.Model);
    }
}
