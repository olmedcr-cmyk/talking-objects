# Seguridad

Si encuentras una vulnerabilidad, **no abras un issue público**. Usa los avisos privados de seguridad de GitHub en este repositorio, o escribe a Divina Machina.

Superficie a tener en cuenta:

- **Claves.** `config.env` y los secretos del Worker (`DEVICE_KEY`, `MCP_KEY`, `ADMIN_KEY`) nunca van al repositorio.
- **El MCP abre el hardware a internet.** Las acciones validan argumentos y tienen cupos en el dispositivo; no añadas acciones sin ambas cosas.
- **La página de estado** es de solo lectura por diseño. No le añadas controles.
- **Datos personales.** El objeto no guarda transcripciones por defecto. Los registros que adjuntes a un issue no deben contener frases de visitantes.
