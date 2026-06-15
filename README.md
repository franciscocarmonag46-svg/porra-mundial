# Porra Mundial 2026

Aplicación web sencilla para una porra de 50/100 usuarios.

## Qué incluye

- Registro e inicio de sesión de usuarios.
- Lista de los 104 partidos del Mundial 2026.
- Predicción por usuario y partido.
- Bloqueo automático cuando llega la hora de inicio.
- Puntuación automática:
  - resultado exacto: 3 puntos
  - acierta ganador/empate/perdedor: 2 puntos
  - falla: 0 puntos
- Clasificación general.
- Panel de administrador para introducir resultados reales.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt
python app.py
```

Abre en el navegador:

```text
http://127.0.0.1:5000
```

## Usuario administrador inicial

```text
usuario: admin
contraseña: admin123
```

Cámbialo antes de publicarlo.

## Notas

- La base de datos se crea automáticamente en `porra.db` al arrancar.
- Las horas están cargadas como hora de España peninsular aproximada a partir de horarios publicados en UK time, sumando 1 hora.
- Para subirlo a internet, lo ideal sería usar Render, Railway o un VPS sencillo.
