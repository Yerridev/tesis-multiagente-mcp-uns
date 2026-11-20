@echo off
chcp 65001 >nul
echo ============================================================
echo  07.2 - QUE WEB ESTOY VIENDO (diagnostico, no cambia nada)
echo ============================================================
echo.
echo [1/3] Contenedores web corriendo (nombre / puertos):
docker ps --filter name=frontend --format "  {{.Names}}  ->  {{.Ports}}  ({{.Status}})"
echo.
echo [2/3] Imagen que usa mcp-frontend y cuando se creo:
docker inspect -f "  imagen {{.Image}}  creado {{.Created}}" mcp-frontend
echo.
echo [3/3] Texto dentro de la web servida por mcp-frontend:
docker exec mcp-frontend sh -c "grep -l 'FastAPI' /usr/share/nginx/html/assets/*.js >/dev/null && echo   CONTIENE: Python FastAPI   [version nueva] || echo   NO contiene FastAPI   [version vieja]"
docker exec mcp-frontend sh -c "grep -l 'ASP.NET Core' /usr/share/nginx/html/assets/*.js >/dev/null && echo   CONTIENE: ASP.NET Core || echo   no contiene ASP.NET"
echo.
echo Pasame esto y la direccion que tienes en la barra del navegador.
pause
