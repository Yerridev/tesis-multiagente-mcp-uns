using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace MCP.Industrial.Api;

public sealed class OpenRouterOptions
{
    public string? ApiKey { get; set; }
    public string Model { get; set; } = "openrouter/free";
    public int MaxTokens { get; set; } = 1600;
    public int TimeoutSeconds { get; set; } = 90;
}

public sealed record LlmResult(bool Ok, string? Model, string? Text, string? Error, long Ms);

/// <summary>Modelo que el operador puede elegir en el chat (lista cerrada: el navegador no puede pedir otro).</summary>
public sealed record ModeloIa(string Id, string Nombre, bool Gratis);

/// <summary>
/// Cliente mínimo de OpenRouter. La clave vive SOLO en el backend
/// (appsettings.json o la variable de entorno OPENROUTER_API_KEY): jamás se expone al navegador.
/// </summary>
public sealed class OpenRouterAgent
{
    private readonly HttpClient _http;
    private readonly OpenRouterOptions _options;

    public OpenRouterAgent(IConfiguration configuration, IHttpClientFactory httpClientFactory)
    {
        _options = configuration.GetSection("OpenRouter").Get<OpenRouterOptions>() ?? new OpenRouterOptions();
        var fromEnv = Environment.GetEnvironmentVariable("OPENROUTER_API_KEY");
        if (!string.IsNullOrWhiteSpace(fromEnv)) _options.ApiKey = fromEnv;
        var modelEnv = Environment.GetEnvironmentVariable("OPENROUTER_MODEL");
        if (!string.IsNullOrWhiteSpace(modelEnv)) _options.Model = modelEnv;

        /* Catálogo elegible desde el chat. OPENROUTER_MODELS = "id|Nombre,id2|Nombre2".
           El primero es el predeterminado si OPENROUTER_MODEL no está en la lista. */
        var lista = Environment.GetEnvironmentVariable("OPENROUTER_MODELS");
        if (string.IsNullOrWhiteSpace(lista))
            lista = $"{_options.Model}|{Corto(_options.Model)},nvidia/nemotron-3-ultra-550b-a55b:free|Nemotron 3 Ultra,google/gemma-4-31b-it:free|Gemma 4 31B,openrouter/free|Auto gratis";
        foreach (var item in lista.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var partes = item.Split('|', 2, StringSplitOptions.TrimEntries);
            var id = partes[0];
            if (id.Length == 0 || Modelos.Any(x => x.Id == id)) continue;
            Modelos.Add(new ModeloIa(id, partes.Length > 1 && partes[1].Length > 0 ? partes[1] : Corto(id), id.EndsWith(":free") || id == "openrouter/free"));
        }
        if (!Modelos.Any(x => x.Id == _options.Model)) Modelos.Insert(0, new ModeloIa(_options.Model, Corto(_options.Model), _options.Model.EndsWith(":free")));

        _http = httpClientFactory.CreateClient("openrouter");
        _http.Timeout = TimeSpan.FromSeconds(Math.Max(10, _options.TimeoutSeconds));
    }

    public bool Enabled => !string.IsNullOrWhiteSpace(_options.ApiKey);
    public string Model => _options.Model;
    public List<ModeloIa> Modelos { get; } = [];

    /// <summary>Nombre legible a partir del id del modelo.</summary>
    private static string Corto(string id)
    {
        var c = (id.Contains('/') ? id[(id.LastIndexOf('/') + 1)..] : id).Replace(":free", "");
        return string.Join(' ', c.Split('-', StringSplitOptions.RemoveEmptyEntries)
            .Select(p => char.IsLetter(p[0]) ? char.ToUpperInvariant(p[0]) + p[1..] : p));   // "claude-haiku-5.5" → "Claude Haiku 5.5"
    }

    /// <summary>Solo modelos del catálogo; cualquier otro valor usa el predeterminado.</summary>
    public string Resolver(string? pedido) =>
        !string.IsNullOrWhiteSpace(pedido) && Modelos.Any(x => x.Id == pedido) ? pedido : _options.Model;

    public async Task<LlmResult> CompleteAsync(string system, string user, CancellationToken token, string? modelo = null)
    {
        var elegido = Resolver(modelo);
        if (!Enabled) return new LlmResult(false, elegido, null, "sin clave de OpenRouter configurada", 0);

        var started = System.Diagnostics.Stopwatch.StartNew();
        try
        {
            var payload = new
            {
                model = elegido,
                max_tokens = _options.MaxTokens,
                messages = new object[]
                {
                    new { role = "system", content = system },
                    new { role = "user", content = user },
                },
            };

            using var request = new HttpRequestMessage(HttpMethod.Post, "https://openrouter.ai/api/v1/chat/completions")
            {
                Content = JsonContent.Create(payload, options: new JsonSerializerOptions
                {
                    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
                }),
            };
            request.Headers.TryAddWithoutValidation("Authorization", $"Bearer {_options.ApiKey}");
            request.Headers.TryAddWithoutValidation("HTTP-Referer", "http://127.0.0.1:5050");
            request.Headers.TryAddWithoutValidation("X-Title", "MCP-Industrial");

            using var response = await _http.SendAsync(request, token);
            var body = await response.Content.ReadAsStringAsync(token);
            started.Stop();

            if (!response.IsSuccessStatusCode)
                return new LlmResult(false, elegido, null, (int)response.StatusCode == 429 ? "límite de consultas del modelo alcanzado (429): elige otro modelo" : $"OpenRouter respondió {(int)response.StatusCode}", started.ElapsedMilliseconds);

            using var doc = JsonDocument.Parse(body);
            var root = doc.RootElement;
            var model = root.TryGetProperty("model", out var m) ? m.GetString() : elegido;
            string? text = null;
            if (root.TryGetProperty("choices", out var choices) && choices.GetArrayLength() > 0)
            {
                var message = choices[0].GetProperty("message");
                if (message.TryGetProperty("content", out var content)) text = content.GetString();
                if (string.IsNullOrWhiteSpace(text) && message.TryGetProperty("reasoning", out _))
                    return new LlmResult(false, model, null, "el modelo devolvió solo razonamiento sin respuesta", started.ElapsedMilliseconds);
            }

            return string.IsNullOrWhiteSpace(text)
                ? new LlmResult(false, model, null, "respuesta vacía del modelo", started.ElapsedMilliseconds)
                : new LlmResult(true, model, text.Trim(), null, started.ElapsedMilliseconds);
        }
        catch (OperationCanceledException)
        {
            started.Stop();
            return new LlmResult(false, elegido, null, "tiempo de espera agotado", started.ElapsedMilliseconds);
        }
        catch (Exception ex)
        {
            started.Stop();
            return new LlmResult(false, elegido, null, ex.Message, started.ElapsedMilliseconds);
        }
    }
}
