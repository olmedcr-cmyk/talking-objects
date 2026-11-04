# Contribuir

Gracias por querer mejorar los objetos que conversan.

## Antes de empezar

```bash
make setup && make test && make lint
make worker-setup && make worker-test
```

## Criterios

- **Nada tumba una conversación.** Un periférico que falla registra el error y sigue. Si falta una librería, el módulo degrada a no-op.
- **Una sola puerta al hardware.** Las acciones nuevas pasan por `ActionRegistry`, con `validate`, esquema JSON y cupo.
- **Privacidad por defecto.** Nada nuevo guarda o envía lo que dice un visitante sin que alguien lo active a propósito.
- **Código y comentarios en inglés; documentación en español**, con el README también en inglés.
- **Comentarios que explican el porqué.** Lo que se aprendió en campo merece quedar escrito junto al código.
- **Tests** para la lógica (acciones, reglas, relevo, protocolo). Lo que toca hardware se prueba en una Pi y se dice en el PR.

## Commits

Mensajes cortos en imperativo, en español o en inglés: «Añade relé de humo», «Fix LED idle color parsing».
