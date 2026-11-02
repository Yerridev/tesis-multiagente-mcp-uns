# tesis-mcp-multiagent-uns

Bosquejo funcional: ASP.NET Core 10 + SignalR y React + TypeScript + Vite. Presenta telemetría simulada de caudal, nivel y presión. No escribe en ningún PLC.

Compilar frontend: `cd frontend; npm run build`

Copiar `frontend/dist` dentro de `backend/wwwroot` y ejecutar: `cd backend; dotnet run --urls http://localhost:5051`

Abrir `http://localhost:5051`.
