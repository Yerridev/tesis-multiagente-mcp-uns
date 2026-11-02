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

        _http = httpClientFactory.CreateClient("openrouter");
        _http.Timeout = TimeSpan.FromSeconds(Math.Max(10, _options.TimeoutSeconds));
    }

    public bool Enabled => !string.IsNullOrWhiteSpace(_options.ApiKey);
    public string Model => _options.Model;

    public async Task<LlmResult> CompleteAsync(string system, string user, CancellationToken token)
    {
        if (!Enabled) return new LlmResult(false, _options.Model, null, "sin clave de OpenRouter configurada", 0);

        var started = System.Diagnostics.Stopwatch.StartNew();
        try
        {
            var payload = new
            {
                model = _options.Model,
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
                return new LlmResult(false, _options.Model, null, $"OpenRouter respondió {(int)response.StatusCode}", started.ElapsedMilliseconds);

            using var doc = JsonDocument.Parse(body);
            var root = doc.RootElement;
            var model = root.TryGetProperty("model", out var m) ? m.GetString() : _options.Model;
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
            return new LlmResult(false, _options.Model, null, "tiempo de espera agotado", started.ElapsedMilliseconds);
        }
        catch (Exception ex)
        {
            started.Stop();
            return new LlmResult(false, _options.Model, null, ex.Message, started.ElapsedMilliseconds);
        }
    }
}
