# Plataforma conversacional transaccional — informe de arquitectura

> Diseño técnico de una plataforma conversacional multi-cliente y transaccional
> para centros de contacto (voz y chat), preparado para el reto de *Principal
> Platform Architect* de ABAI. Cubre los trece entregables del enunciado. Cada
> afirmación se apoya en código de este repositorio, en un comando que se puede
> ejecutar o en una sesión real que se puede releer; el índice está en el
> **Apéndice A**.

Este documento y el mazo de catorce láminas (`presentation/`, `npm run pdf`)
dicen lo mismo con distinta densidad: el mazo acompaña una exposición, este
informe se lee solo. Los números son los mismos en los dos, y salen de las mismas
llamadas.

**Tesis.** El LLM es un *driver* de interfaz intercambiable; la plataforma es un
runtime de procesos que habla. El control, el estado, las tools, la auditoría y
la tenencia viven en el backend, nunca en el prompt.

---

> **Layout note (ms-23, 2026-09-03).** Paths in this report predate the refactor that moved
> `core/`, `api.py` and `worker.py` under the single package `convo/` and turned the prompt
> modules into Markdown views. Read `core/x` as `convo/…/x`; the current map is in `README.md`.

## 0. Resumen ejecutivo

Hay una plataforma corriendo. Un número de teléfono real (`+1 417 674 3169`)
entra por una troncal SIP a una caja propia, la atiende un worker, el worker
habla con un modelo pequeño, y todo lo que pasa queda escrito en un log
append-only que se puede releer entero desde la terminal. La sesión
`AJ_rdrkYph3FaeS` —una llamada de voz de 1 m 11 s, 13 turnos, 88 eventos,
0,0063 € de proveedores y score 0,96— es de donde sale la mayoría de los números
de este informe.

Tres ideas sostienen el diseño:

1. **Determinismo donde se mueve dinero.** El modelo puede *pedir* una
   confirmación; sólo `ConfirmTask` puede *acuñarla*. `guard.check` rechaza
   cualquier tool marcada `irreversible` que no traiga un `confirmation_token`
   válido. La autoridad no está en el prompt y, por tanto, no depende de que el
   modelo obedezca.
2. **La tenencia es dato, no despliegue.** Una flota, muchos negocios. La
   identidad del cliente llega en los metadatos del dispatch y se resuelve una
   sola vez en un `TenantContext`. Cambiar la voz, el modelo o el prompt de un
   proyecto es una fila en una tabla, no una release.
3. **Auditable por construcción.** El log se escribe *durante* la llamada, con
   un `seq` por sesión y disparadores de SQLite que abortan `UPDATE` y `DELETE`.
   Un `SIGKILL` se lleva la llamada; nunca la prueba de lo que ya había pasado.

Lo que **no** hemos construido está dicho en voz alta a lo largo del documento:
el protocolo remote-tenant está especificado y no implementado (§8), el
re-enganche de una llamada caída está decidido y no construido (§6), y la lista
de lo que queda fuera a propósito está en §13.

---

## 1. Arquitectura de alto nivel (E-1)

El sistema se separa en **tres planos**, que corren por separado hoy:

| Plano | Proceso | Qué posee |
|---|---|---|
| Datos | `worker.py` | la conversación viva: media, STT, LLM, TTS, tools |
| Control | `api.py` | rutas, versiones de proyecto, overrides, tokens, consola |
| Evidencia | el log y la CLI | lo que pasó, numerado y no editable |

El camino de una llamada es: canal (SIP/PSTN, WebRTC o chat) → LiveKit (SFU y
puente SIP, autohospedado) → **un job por llamada** → plano de control por HTTP →
tools (locales, adaptadores, remotas) → sistemas del cliente.

La frontera que más decide es la del proceso. **Un job es un proceso del sistema
operativo y no abre ninguna conexión a base de datos ni ningún pool**: todo el IO
de negocio sale por HTTP contra `api.py` a través de `core/control_plane.py`. La
alternativa —un worker con conexiones directas a la base— ahorra un salto de red
y a cambio deja que una conversación cualquiera corrompa el estado de todas, y
convierte cada llamada colgada a destiempo en una conexión huérfana. Matar una
llamada aquí se lleva esa llamada y nada más.

El LLM aparece **dentro** de una de las cajas del diagrama, no alrededor de él.
Es un nodo del sistema, con un contrato de entrada y otro de salida, y es
sustituible: `core/providers/llm.py` despacha por familia de modelo —`claude-*`
construye el plugin de Anthropic, `gpt-*` el de OpenAI— contra una
`ALLOWED_MODELS` que es la lista corta de modelos que alguien ha medido y
tarifado.

El precalentamiento (`setup_fnc`) sólo carga el VAD y el detector de turno, con
un presupuesto de diez segundos; nada de negocio se calienta ahí, porque nada de
negocio vive en ese proceso.

**Validación.** Los tres planos se levantan por separado: `python worker.py dev`,
`uvicorn api:app --port 8090` y `python -m convo sessions show AJ_rdrkYph3FaeS`.

---

## 2. Dominios y bounded contexts (E-2)

Siete contextos, cada uno con lo que posee y lo que se niega a hacer:

| Contexto | Qué posee | Qué se niega a hacer |
|---|---|---|
| Session | el turno vivo, la etapa, el canal | guardar estado propio fuera del log |
| Process | etapas, saga, confirmación, compensación | delegar la autoridad al prompt |
| Tools & Adapters | el `ToolSpec`, el guard, los puertos | ejecutar `irreversible` sin token |
| Tenancy & Config | rutas, proyectos, versiones, overrides | resolverse en tiempo de compilación |
| Audit | el log append-only con `seq` y el informe | editar o reordenar un evento escrito |
| Evaluation | goldens, DAGs, réplicas, el juicio por llamada | entrar en el camino de producción |
| Supervision | el ticket de observador y los verbos de escucha | conceder más de lo que firmó el ticket |

Los contextos no se declaran en un diagrama: se declaran en el árbol de
directorios y **los obliga un test**. `core/` es el runtime y no importa ningún
tenant; los tenants importan `core`, nunca al revés.
`tests/test_core_isolation.py` recorre los 108 módulos de `core/` y falla si
alguno nombra `tenants`. La alternativa —un runtime que conoce a sus clientes—
convierte cada alta de negocio en una release de la plataforma.

Los proyectos importan `core.agents` (`TenantAgent`, `ConfirmTask`, …) y nunca
`livekit.agents.voice` directamente: el framework subyacente es sustituible desde
un solo paquete.

**El contexto delgado a propósito es Tools & Adapters.** `ToolExecutor` es un
`Protocol` y hoy tiene una sola implementación, la local. El mismo contrato
debería poder ejecutarse en el proceso del cliente; la frontera está escrita y
falta cruzarla (§8).

---

## 3. Modelo de ejecución de una conversación (E-3)

**Un turno es una transacción con log, no una respuesta.**

El turno lo cierra la máquina, no el modelo. El *endpointing* del STT y un
detector de turno local en CPU comparten la decisión; una interrupción necesita
más de una palabra, porque un «vale» a media frase es un asentimiento y no el
turno del llamante. VAD y detector de turno corren en CPU (`silero`,
turn-detector v1-mini): **no hay GPU en el inventario**, a propósito.

La secuencia de un turno con escritura es:

```
audio → STT (parciales) → final → turno cerrado → LLM → tool_call
     → guard.check → ConfirmTask pregunta → «sí» → token acuñado
     → tool ejecutada + compensación declarada → respuesta → TTS
```

y a la derecha de todo eso, en paralelo, el log append-only: `stt.final`,
`turn.user`, `tool.call`, `tool.refused`, `confirm.request`, `confirm.granted`,
`tool.result`, `turn.agent`, `session.end`. **Se escribe durante el turno, no al
colgar.**

### Latencias medidas

Sobre la sesión `AJ_rdrkYph3FaeS`, 13 turnos:

| Tramo | Medida |
|---|---|
| Transcripción (final del STT) | 0,47 s |
| ttft del LLM | 0,64 s (máx. 1,01 s) |
| ttfb del TTS | 0,11 s |
| Extremo a extremo del turno | 3,31 s |

### Los caminos de fallo, en el mismo diagrama

- **Error de proveedor.** La tool falla con `ToolError` y el modelo lee el
  motivo, porque ese mensaje es una frase que el llamante podría oír. Cualquier
  otra excepción queda oculta al modelo y se registra como `tool.error`. El turno
  sigue; la llamada no muere.
- **`tool_use` huérfano.** `sanitize_tool_pairing(chat_ctx)` corre antes de cada
  generación. Un par roto devuelve un 400 de Anthropic y deja la conversación
  inservible hasta colgar: no es un caso raro, es el fallo más caro de la
  integración.
- **Caída a mitad de saga.** Se ejecuta la compensación declarada en el
  `ToolSpec`, en orden inverso. La sesión no se reanuda: se re-engancha (§6).

---

## 4. Diseño de tools y contratos (E-4)

**Ninguna función es una tool hasta que declara qué le hace al mundo.** El
contrato se lee dos veces: una la máquina y otra el modelo.

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    side_effect: SideEffect          # read | write | irreversible
    idempotency_key: str | None = None
    pii_scope: frozenset[str] = field(default_factory=frozenset)
    timeout_s: float = 8.0
    compensation: str | None = None
    result_summary: Callable[[Any], str] | None = None
    infrastructure: bool = False
```

Una tool real declarada con él:

```python
BOOK_SLOT = ToolSpec(
    name="book_slot",
    side_effect=SideEffect.IRREVERSIBLE,      # exige token de confirmación
    idempotency_key="slot_id",                # un reintento no reserva dos veces
    pii_scope=frozenset({"phone", "patient"}),
    compensation="cancel_slot",               # el deshacer, declarado
    timeout_s=8.0,
    result_summary=summarise_change,          # la única línea que el log guarda
)
```

Cuatro propiedades del diseño:

1. **El efecto decide, no el nombre.** `side_effect` gobierna confirmación,
   reintentos y registro. El tablero de transacciones cuenta operaciones leyendo
   `irreversible` del log, nunca una lista de nombres mantenida a mano.
2. **El fallo tiene dos audiencias.** `ToolError` es la única excepción que el
   modelo lee, y su mensaje se escribe para que un llamante pueda oírlo. Lo demás
   se traduce a un fallo genérico; la causa real va al log.
3. **El log guarda la forma, no el resultado.** `tool.result` registra `list[3]`,
   jamás la fila de la agenda. `result_summary` es opcional y su salida pasa por
   la máscara de PII.
4. **Un contrato, tres ejecutores.** El docstring es el esquema que ve el modelo
   —se escribe para el modelo, no para el lector humano— y el `ToolSpec` es lo
   que lee la plataforma. Una tool local, un adaptador REST y una tool remota
   comparten contrato y cambian sólo de ejecutor.

**Validación.** `core/tools/contract.py` y `core/tools/executor.py`, con 20 tests
en `tests/test_tools.py`; entre ellos
`an_adapter_that_explodes_never_leaks_its_stack_trace_to_the_llm` y
`a_renderer_that_explodes_costs_the_log_a_line_and_the_caller_nothing`.

---

## 5. Orquestación transaccional (E-5)

### El consentimiento es un paso de la saga, no una frase del prompt

Confiar en que el modelo no reserve antes de tiempo tiene un problema que no es
de calidad sino de forma: **cuando el modelo se salta la instrucción no hay
excepción, hay una cita reservada que nadie pidió**. Un token sí falla, y falla
donde se puede leer.

El consentimiento va en dos fases:

**Fase 1 — pedir.** La tool que llama el modelo (`book_appointment`) no escribe:
devuelve una pregunta de confirmación **redactada por la plataforma**, no por el
modelo, y cede el turno a `ConfirmTask`, cuya única salida posible es *confirm* o
*decline*. Con *decline* no se escribe nada.

**Fase 2 — autorizar y escribir.** Con un *confirm*, `confirm.mint` acuña un
token cuya audiencia es `sha256(tool + argumentos canónicos)` y cuyo TTL es de
120 segundos. La saga ejecuta sus pasos (`cancel → book_slot → send_sms`) y
`guard.check` deja pasar la escritura `irreversible` porque —y sólo porque— el
token corresponde a esa llamada exacta, con esos argumentos, una vez.

**El guard rechaza de cuatro formas**: sin token, con un token de otra llamada,
con uno caducado y con uno ya gastado. Las cuatro son `ToolRefused`, que el
modelo nunca ve como excepción cruda.

### Compensación e idempotencia

La compensación **se declara, no se improvisa**: cada `ToolSpec` nombra su
deshacer, y la saga los ejecuta en orden inverso sobre los pasos completados.
Deshacer es siempre `write`, nunca `irreversible` — un `cancel_slot` no puede
exigir a su vez una confirmación a un llamante que ya colgó.

`idempotency_key` nombra el intento, no la llamada: un reintento tras un timeout
de red no reserva dos veces. El token se gasta al **acertar**; una llamada
fallida deja el «sí» vivo sus 120 s y la etapa reintenta sin volver a preguntar.

### Si el llamante cuelga entre el «sí» y la escritura

El proceso muere con la llamada. No hay escritura a medias porque no hay
escritura: lo que queda es un `tool.call` sin resultado, que el tablero de
transacciones muestra como pendiente.

### El humano como paso de la orquestación

Un supervisor entra en una llamada viva con un **ticket firmado de quince
minutos**, y la capacidad va dentro del token, no en la pantalla:

| Capacidad | Lo que firma el ticket | Qué concede |
|---|---|---|
| `listen` | publish no · data no · hidden sí | escucha oculta |
| `whisper` | publish no · data sí · hidden sí | texto al agente, que el llamante no oye |
| `takeover` | publish sí · data sí · hidden no | micrófono real, participante visible |

La consola **no concede nada**: enumera lo que el ticket ya permite. La
alternativa —un botón que autoriza hablar— deja el permiso en el cliente que lo
dibuja. La identidad la pone el SFU en cada paquete y en cada RPC (`sup:<uid>`),
así que ningún payload puede reclamarla; una misma identidad asciende de `listen`
a `takeover` sin abrir una segunda conexión.

Cada verbo se anexa **al log del llamante**, con su propio `seq`: una llamada
sigue siendo una sola historia aunque la hayan tocado dos personas. Que se avise
o no de la escucha es una decisión por tenant, no una constante del código.

**Validación.** Ring de consentimiento: 8 de 8 llamadas simuladas a 1,00, tanto
en `claude-haiku-4-5` como en `gpt-5.4-mini`. Las cuatro negativas del guard son
7 tests en `tests/test_confirm.py`; el escritorio de supervisión, 16 en
`tests/test_supervisor_desk.py`. En producción, sesión `AJ_rdrkYph3FaeS`:
`seq 39` pregunta, `seq 46` concede, `seq 51` escribe.

---

## 6. Gestión de estado (E-6)

**El estado es un log, no un objeto.** Lo que hay que saber de una conversación
es la lista ordenada de lo que le pasó. Guardar en su lugar un objeto de sesión y
volcarlo al colgar convierte cada `SIGKILL` en una llamada sin historia — se
pierde justo la prueba de lo que ya había ocurrido.

- **Qué es estado.** El log, y tres tablas que el router lee antes de empezar:
  `routes`, `project_versions`, `pipeline_overrides`. Nada más sobrevive al
  proceso.
- **Qué es derivado.** El resultado, el coste, el score y el tablero de
  transacciones se calculan al leer, sobre los mismos eventos. No hay ningún
  contador junto a la escritura y, por tanto, no hay ningún contador que
  desincronizar.
- **Qué no se persiste, a propósito.** El contenido de un resultado. Un log con
  las filas de la agenda guardaría las horas del paciente al lado de su nombre
  enmascarado, que es exactamente lo que la máscara evita.

`EventLog.append` llega a SQLite (WAL, `synchronous=FULL`) antes de retornar, y
dos disparadores abortan `UPDATE` y `DELETE` sobre `events`. La clave primaria es
`(session_id, seq)`.

**El handoff entre etapas no copia historia.** El resumen de la etapa anterior se
reescribe en `TenantAgent.on_enter` leyendo `tc.prev_agent.chat_ctx`, y se coloca
*detrás* del prefijo compartido, que sigue siendo byte a byte el mismo y sigue
cacheado.

### Re-enganche, no reanudación — decidido, sin construir

Una llamada caída es una **sala nueva y un job nuevo**: el proceso murió con
ella, así que no hay sesión que reanudar. Lo que puede volver es el *estado*: una
instantánea de `ChatContext.to_dict()` más la etapa, indexada por
`sip.phoneNumber` y rehidratada en la siguiente entrante dentro de N minutos.

Hoy esa segunda llamada empieza de cero: `git grep rehydrate core/` no devuelve
nada. Está decidido y documentado; no está construido.

**Validación.** `tests/test_sigkill.py` mata al escritor en el evento 30 y relee
`seq 1..31` sin huecos. La sesión `AJ_rdrkYph3FaeS` son 88 eventos y 13 turnos,
legibles enteros con `python -m convo sessions show`.

---

## 7. Configuración por cliente y proyecto (E-7)

**Dar de alta un negocio no es desplegar.** Quién llama llega en los metadatos
del dispatch —regla de dispatch para SIP, `RoomAgentDispatch` dentro del JWT para
WebRTC— y se resuelve una sola vez, en `core/router.resolve`, a un único
`TenantContext`, la única definición de ese objeto en el árbol. El **canal** (voz
o chat) pertenece a la sesión, no al proyecto.

La línea entre código y configuración está trazada así:

| Qué | Dónde vive | Cómo cambia |
|---|---|---|
| Etapas, tools y sus `ToolSpec` | `tenants/<t>/projects/<p>/`, en git | Release. Es código y se revisa como código. |
| Prompt y bloque de conocimiento | git es la semilla; `project_versions` la fija | Una fila. La versión con la que corrió va en el primer evento de la sesión. |
| Voz, modelo TTS, modelo LLM, oído STT, saludo | `pipeline_overrides` | Un `PUT` desde la consola. La siguiente sesión ya lo resuelve. |
| Qué número atiende a qué proyecto | `routes` | Una fila. Un teléfono es una ruta, nunca un proyecto. |

**En caliente no significa sin reglas.** `OVERRIDABLE` son cinco campos
concretos, no un permiso general, y un valor que la plataforma no sabe correr se
rechaza dos veces: al guardarlo y al construir el pipeline. La consola muestra el
pipeline que la **próxima** llamada va a correr, con la allow-list y el modelo que
la plataforma se niega a arrancar.

**Radio de daño.** `core/registry.py` importa cada tenant en su propio
`try/except`: un `tenant.py` que no importa queda fuera del registro y sus
llamadas no son enrutables, mientras las de los demás siguen entrando. Un negocio
roto no tumba la flota.

**Validación.** 31 tests de enrutado, overrides y aislamiento, entre ellos
`test_a_put_changes_what_the_next_session_resolves_to`,
`test_a_project_with_no_override_resolves_exactly_as_git_deployed_it` y
`test_a_broken_tenant_folder_is_unroutable_and_the_others_still_serve`. Dos
negocios —`clinica-norte` y `tienda-sur`— corren hoy sobre un solo worker:
`python worker.py console --tenant tienda-sur`.

---

## 8. Integración con sistemas externos (E-8)

**Integrar no es abrirnos un puerto en la red del cliente: es que su proceso
salga hacia nosotros.**

### Hoy — en producción

El tenant es un paquete en nuestro árbol: `tenants/<t>/`, un `Adapter` por
sistema suyo (agenda, CRM, ERP, SMS) y las tools declaradas en su proyecto.
Salimos nosotros hacia su API; nadie tiene que abrirnos nada. Mientras esa API no
exista, el adaptador es un doble con la misma firma, y todo lo que está por
encima —guard, log, consentimiento, máscara de PII— ya funciona contra él.

**Lo que cuesta:** el cliente depende de nuestro ciclo de release. Cambiar una
tool suya es un despliegue nuestro y una revisión nuestra. Es una deuda
reconocida, no un descuido.

### Mañana — diseñado, no implementado

El tenant vive en el proceso del cliente: sus etapas, sus tools y sus prompts,
hablando con nosotros a través de un SDK. La conexión es un **WebSocket
saliente** contra el plano de control: ni agujero de firewall entrante, ni
webhook que firmar y rotar. Quien tiene que abrir un puerto es nadie.

Las tramas del protocolo:

```
→  hello          {tenant, sdk, proto}
→  register       {manifest: stages · tools[{name, schema, ToolSpec}] · prompts_hash}
⇄  ping / pong    la conexión ES el registro: sin latido, el tenant no es enrutable
←  session.start  {session_id, project, channel}
←  invoke         {invocation_id, tool, args, deadline}
→  result         {invocation_id, payload}
→  fail           {invocation_id, message, retriable}
```

**Qué pasa en una caída a mitad de `invoke`:** el `deadline` es el `timeout_s`
del `ToolSpec`; vencido, la plataforma levanta `ToolError` y la etapa ofrece un
humano. Una segunda conexión del mismo tenant sustituye a la primera, que se
cierra con motivo.

**Lo que no viaja.** `guard.check` rechaza una tool `irreversible` sin
`confirmation_token` **antes de que salga un byte**; el log append-only sigue
siendo nuestro; y un argumento marcado en `pii_scope` nunca llega entero a él. La
autoridad no se muda al proceso del cliente aunque el código sí.

**Validación.** El hueco ya existe en el código: `ToolExecutor` es un `Protocol`
en `core/tools/executor.py` y `LocalExecutor` es hoy su única implementación —
un ejecutor remoto es una segunda clase, y nada por encima de esa línea cambia.
El protocolo está especificado en las cards `tk-1265f0`, `tk-061906` y
`tk-8289fb` del hito ms-12, hoy sin implementar: es la fase siguiente del roadmap.

---

## 9. Observabilidad, auditoría, replay y QA (E-9)

**Cuatro anillos, un solo vocabulario.** Un anillo cambia de dónde viene la
conversación, nunca cómo se juzga: las mismas métricas puntúan un golden en CI,
una llamada de madrugada, una sesión real reproducida y la llamada que acaba de
colgar.

| Anillo | Qué evalúa | Cuándo |
|---|---|---|
| 1 | goldens por proyecto, en texto, más conversaciones simuladas | CI, en cada push |
| 2 | **voz**: offline una llamada grabada; en vivo un llamante sintético que habla de verdad | offline a demanda; en vivo, nocturna a las 04:00 Europe/Madrid |
| 3 | **sesiones reales almacenadas**, reproducidas por las mismas métricas | a demanda, `python -m convo sessions eval <id>` |
| 4 | **toda llamada, automáticamente** | sin que nadie lo pida, un minuto después de colgar |

**Ninguna métrica juzgada corre en el anillo unitario.** `pytest -m unit` es una
puerta: tiene que estar verde tres veces de tres o deja de significar algo, y un
juez no da esa garantía.

### El anillo 4 — toda llamada se puntúa sola

Cuatro comprobaciones decididas **por código** —consentimiento, registro, fuga
entre tenants, errores de proveedor— más **como mucho un juicio** de Haiku. El
resultado queda como `session.score` con el siguiente `seq` del mismo log, unos
cinco segundos después de colgar. Coste medido: **0,0014 €**; **0 €** si el
llamante colgó en el saludo, porque el juez se salta por debajo de tres turnos.
El techo de gasto (0,0100 €) se comprueba *antes* de gastarlo.

La concurrencia se resuelve sola: `session.score` toma `max(seq) + 1` y la clave
primaria es `(session_id, seq)` bajo disparadores append-only. Dos planos de
control sobre una misma base es una forma soportada — uno gana, el otro lee el
rechazo y reporta que otro llegó antes. Sin lock, sin columna de estado, sin
ventana.

### Replay

El log es completo: `convo sessions eval <id>` re-ejecuta los turnos **sin el
audio** y les pasa las métricas del anillo 1. Eso es lo que hace que una queja
sobre una llamada concreta sea una prueba reproducible y no un recuerdo.

### La matriz de modelos — un `goldens.json`, dos modelos

La tesis de esta plataforma es que el LLM es intercambiable. Eso es una
afirmación, y el anillo 1 es donde se demuestra o se queda en conversación: los
mismos goldens, las mismas métricas, los mismos umbrales, contra cada modelo que
la plataforma va a servir.

**clinica-norte / reagendamiento — 17 goldens** (31-08-2026):

| Métrica | claude-haiku-4-5 | gpt-5.4-mini |
|---|---|---|
| Grounded facts [DAG] | 17/17 · 1,00 | 17/17 · 1,00 |
| Keeps the register [DAG] | 17/17 · 1,00 | 17/17 · 1,00 |
| Reception line [GEval] | 17/17 · 0,87 | 16/17 (94 %) · 0,87 |
| Tool Correctness | 17/17 · 1,00 | 16/17 (94 %) · 0,94 |

**tienda-sur / pedidos — 11 goldens**:

| Métrica | claude-haiku-4-5 | gpt-5.4-mini |
|---|---|---|
| Grounded facts [DAG] | 11/11 · 1,00 | 11/11 · 1,00 |
| Keeps the register [DAG] | 11/11 · 1,00 | 11/11 · 1,00 |
| Order desk line [GEval] | 9/11 (82 %) · 0,86 | 10/11 (91 %) · 0,92 |
| Tool Correctness | 10/11 (91 %) · 0,91 | 10/11 (91 %) · 0,91 |

Cinco divergencias sobre 28 goldens, ninguna en las métricas deterministas. **Una
golden que pasa en un modelo y falla en el otro es un hallazgo, nunca una golden
que ablandar.** La del sábado destapó que GPT lee mal su propia salida de agenda:
la agenda devolvió tres huecos el sábado por la mañana y el modelo contestó que
no tenía ninguno.

Un ejemplo de la misma disciplina en la dirección contraria: una golden de
domingo falló porque Haiku contestaba «los domingos cerramos» directamente desde
la hoja de horarios, sin consultar la agenda. La frase que lo arregla —*un día
que das por cerrado se consulta como cualquier otro, porque la hoja dice cuándo
ABRE el centro y sólo la agenda sabe qué está libre*— entró en el bloque de
prompt compartido, y Tool Correctness en Haiku pasó de 14/16 a 17/17. Ablandar la
golden habría escondido una regla de la que la plataforma depende.

### Billing por la misma tubería

El coste va en la misma fila que el score. Seis sesiones reales del 30 y 31-08
cuestan entre **0,0017 €** y **0,0106 €** de LLM, escritas en el `session.end`.
El anillo 1 entero, los dos negocios, cuesta ≈ 0,10 $ y cuatro minutos. La
nocturna tiene un tope de **8 llamadas**: las goldens *son* la factura, y una
suite que no cabe se salta, se nombra y pone la noche en rojo.

**Validación.** `python -m core.testing.report <tenant> <proyecto> --model
claude-haiku-4-5 --model gpt-5.4-mini`; el detalle golden a golden, en
`docs/evals.md §10`.

---

## 10. Seguridad y privacidad (E-10)

Escrito en positivo: lo que la plataforma **concede**, no lo que prohíbe. Cuatro
propiedades, y ninguna pide honestidad al lado no confiable.

| Concesión | Qué lleva la firma | Lo que concede |
|---|---|---|
| `mint_session` | sala `tenant-project-<uuid8>` exacta y `RoomAgentDispatch(metadata)` firmado | un token entra en una sala y sólo en ésa; el chat se acuña con el audio cerrado |
| `mint_supervisor` | identidad `sup:<uid>`, atributo `{role, cap}`, TTL de 15 minutos | escuchar y hablar son dos concesiones distintas, y el ticket dura lo que dura entrar en una llamada |
| `ConfirmTask` | audiencia `sha256(tool + args canónicos)`, un solo uso | un «sí» autoriza esa llamada exacta, una vez, y se consume al usarse |
| troncal SIP | señalización desde los 8 rangos del carrier y `hide_inbound_port` | el teléfono atiende a quien contrata la línea; sin sala no hay job ni gasto |
| `RECORDINGS_TOKEN` | lectura por id de sesión, validado contra `^[A-Za-z0-9_-]{1,128}$` | el audio se pide por identificador, nunca por una ruta que venga en un payload |

### PII por valor, no por campo

`pii_scope` marca el argumento en el contrato; la sesión **recuerda el valor** y
lo tapa allí donde reaparezca, texto libre incluido. El enmascarado va de más
largo a más corto, de modo que el nombre completo cae antes que su primera
palabra. El gateway de SMS recibe `600123456` y el nombre entero: **la máscara es
propiedad de la copia que va al log**, no del dato que va al proveedor.

### Segregación por tenant

No es una comprobación que el SFU haga a posteriori: es la firma misma. Un token
de un negocio no nombra la sala de otro, así que no hay nada que comprobar
después.

### La superficie mínima

El teléfono es la puerta más ruidosa, y es la que ya nos costó un incidente de
fraude SIP en otro proyecto. Aquí la troncal acepta señalización desde los rangos
del carrier y de nadie más, con el puerto de entrada oculto. Los secretos llegan
sólo por entorno; el único `.env` versionado es `.env.example`.

El aislamiento de audio entre supervisores se midió **contando tramas**, no
escuchando eventos: `scripts/isolation_probe.py` mide una cola de ~220 ms por
stream al revocar.

**Validación.** 13 pruebas en `tests/test_pii.py`, sobre las tools reales de un
tenant, fijan que el nombre dentro del cuerpo del SMS no llega al log y que el
gateway sí recibe el valor entero. Los tokens los cubren
`tests/test_api_tokens.py` y `tests/test_supervisor_desk.py`; el mapa completo de
superficies está en `.taskops/reports/security.md`.

---

## 11. Infraestructura cloud y despliegue (E-11)

**Todo el runtime cabe hoy en una VM.** Una `e2-standard-4` en GCP con IP
estática, un dominio y un certificado:

| Unidad | Qué es |
|---|---|
| `caddy 2` | 443, TLS y un solo origen |
| `livekit-server 1.9.1` | 7880 señalización, SFU |
| `livekit-sip 1.12` | 5060/udp, RTP 10000-20000 |
| `redis 7` | loopback; nadie más lo alcanza |
| `convo-worker.service` | `worker.py start`, un proceso por vCPU |
| `convo-api.service` | `uvicorn` 8090, consola y control |
| `tmp/convo.db` | SQLite WAL — un escritor (api), un lector (worker, por HTTP) |

Las cuatro primeras bajo `docker compose` (`infra/compose/box.yml`); las dos
units de systemd comparten directorio y, por tanto, la misma base. Hacia fuera
sólo salen los proveedores (Anthropic, Soniox, ElevenLabs). **Ninguna GPU**: el
detector de turno y el VAD son modelos locales de CPU.

### Escalar con disparadores escritos, no con adjetivos

| El disparador — un hecho | La palanca, y por qué todavía no |
|---|---|
| Llamadas simultáneas ≈ procesos preacondicionados (uno por vCPU; cuatro hoy) | Segunda caja con la misma unit: el worker **sale** hacia el SFU y el reparto lo hace el dispatch por `agent_name`, sin balanceador ni estado que replicar. Falta el `load_fnc` propio. |
| Un segundo proceso que **escriba** | SQLite → Postgres. Con un escritor y un lector no hay contención a esta carga; migrar antes habría sido ceremonia. |
| Una red que bloquea UDP de salida | Escucha TURN/TLS en 443. Diferido por evidencia: la prueba de aceptación se hizo desde 3G y el medio llegó directo al SFU. |
| Un número fuera de esta región | Segundo SFU coordinado por el mismo Redis, con la troncal originando contra el más cercano. Hoy el RTT del medio lo paga quien llama de lejos. |

### CI/CD con los evals como puerta

`ci.yml` corre `ruff` y `pytest -m unit` en cada push, y el anillo 1 entero
cuando hay clave de API: **un cambio de prompt que tira un golden no sale.** La
guarda de la clave es condición de *paso* y no de *job* — `secrets` no existe en
`jobs.<id>.if`, y mientras lo fue el anillo se saltaba en silencio, que es la
peor forma posible de tener una puerta.

### Coste

El coste marginal de una llamada telefónica no lo manda el modelo: el LLM pone
entre 0,0017 € y 0,0106 €, y la pata PSTN de Twilio ≈ 0,0085 $/min.

**Validación.** `ssh convo-box 'sudo docker ps'` y `systemctl status convo-worker
convo-api` — cuatro contenedores y dos units, verificados el 31-08-2026. El
número `+1 417 674 3169` entra por 5060 y lo contesta esta caja.

---

## 12. Roadmap por fases (E-12)

**Las fases no son un plan: son un registro.** Cada hito terminó con un comando
que una persona ejecutó y un informe de lo que se aprendió por las malas, en
`.taskops/reports/ms-N.md`.

| Fase | Hitos | Qué dejó |
|---|---|---|
| 0 · Fundamentos | ms-0 → ms-2 | Contratos y el primer tool con `ToolSpec`. Acabó con el modelo llamando a un adaptador falso. |
| 1 · La conversación transaccional | ms-3 → ms-5, ms-7 | Etapas, `ConfirmTask`, saga, log, dos negocios en un worker y los goldens que los juzgan. |
| 2 · Voz real | ms-6, ms-8, ms-10, ms-11 | LiveKit propio en una caja y un número que contesta. Acabó con una llamada desde un móvil. |
| 3 · El instrumento | ms-9, ms-13 → ms-15, ms-17, ms-19 | La consola: pipeline, sesiones con score y coste, supervisor, evals y grabaciones. |
| 4 · Lo siguiente | ms-12 y lo que dispare cada palanca | Protocolo remote-tenant cuando un cliente pida su propio proceso; re-enganche al caerse una llamada con saga abierta; segunda caja al llenar los procesos de ésta. |

Dieciocho de los veinte hitos del tablero están cerrados. Los dos abiertos son
este mazo y el protocolo remote-tenant, sin implementar a propósito: no se
construye una integración remota antes de tener un cliente remoto que la pida.

---

## 13. Trade-offs principales (E-13)

Cada decisión lleva al lado la opción que descartó. **Una decisión sin
alternativa rechazada no es una decisión.**

| Decisión | Opción descartada | Lo que cuesta haberla descartado |
|---|---|---|
| LiveKit autohospedado — SFU y SIP en nuestra caja | una pila gestionada de voz | Operamos la caja: troncal, certificados y un firewall que ya nos costó un incidente de fraude SIP. A cambio, PSTN, WebRTC y chat sobre **un** runtime, y el audio no sale de casa. |
| Modelos pequeños con caché de prefijo, detrás de una allow-list | un modelo grande en cada turno | Menos margen en razonamiento largo. A cambio, una llamada de 13 turnos cuesta 0,0063 € y cambiar de modelo es configuración de proyecto. |
| STT, LLM y TTS como *slots* con lista de permitidos | fijar un proveedor por capa | Mantener dos integraciones vivas por capa. A cambio, la plataforma se niega a correr un modelo que nadie ha medido. |
| El tenant es un paquete en nuestro árbol | el agente del cliente en su propio proceso | El cliente depende de nuestro ciclo de release. Deuda reconocida: el protocolo de §8 es cómo se salda. |
| El log es la única verdad y todo lo demás se deriva al leer | contadores y agregados junto a la escritura | Cada lectura de tablero recorre eventos. A cambio, no hay ningún agregado que pueda mentir respecto al log. |

### Lo que deliberadamente no construimos

Cola de reintentos propia, almacén de audio a largo plazo y panel de negocio. Los
tres son producto, no plataforma, y los tres tienen una respuesta comprada mejor
que la que escribiríamos. Lo que tendría que ser cierto para construirlos: un
cliente con un SLA de reintento que su propio sistema no cubra; una obligación
legal de retención que la grabación por sesión no satisfaga; y un comprador que
mire el panel más de una vez por semana.

### Lo que está decidido y no construido

- **Re-enganche de una llamada caída** (§6). Decidido, documentado, sin código.
- **Protocolo remote-tenant** (§8). Especificado en tres cards, sin implementar.
- **`load_fnc` propio para el reparto entre cajas** (§11). Reconocido en ms-10.
- **TURN/TLS en 443** (§11). Diferido por evidencia, no por olvido.

---

## Apéndice A — Índice de evidencia

| Afirmación | Dónde se comprueba |
|---|---|
| Los tres planos corren por separado | `python worker.py dev` · `uvicorn api:app --port 8090` · `python -m convo sessions show <id>` |
| `core/` nunca importa `tenants/` | `pytest -m unit tests/test_core_isolation.py` — 108 módulos, cero infractores |
| El contrato de una tool | `core/tools/contract.py`, `core/tools/executor.py` · 20 tests en `tests/test_tools.py` |
| El guard rechaza de cuatro formas | 7 tests en `tests/test_confirm.py` |
| Consentimiento en una llamada real | sesión `AJ_rdrkYph3FaeS`: `seq 39` pregunta, `seq 46` concede, `seq 51` escribe |
| El log sobrevive a un `SIGKILL` | `tests/test_sigkill.py` — muere en el evento 30, relee `seq 1..31` sin huecos |
| Un override cambia la siguiente sesión | `test_a_put_changes_what_the_next_session_resolves_to`, entre 31 tests de enrutado |
| Un tenant roto no tumba la flota | `test_a_broken_tenant_folder_is_unroutable_and_the_others_still_serve` |
| La PII no llega al log | 13 pruebas en `tests/test_pii.py` |
| El escritorio de supervisión | 16 pruebas en `tests/test_supervisor_desk.py` · `scripts/isolation_probe.py` (~220 ms) |
| La matriz de modelos | `python -m core.testing.report <tenant> <proyecto> --model claude-haiku-4-5 --model gpt-5.4-mini` · `docs/evals.md §10` |
| El coste por llamada | el `session.end` de las seis sesiones del 30 y 31-08: 0,0017 €–0,0106 € |
| Lo que corre en la caja | `ssh convo-box 'sudo docker ps'` · `systemctl status convo-worker convo-api` |
| El teléfono | llamar al `+1 417 674 3169` |
| El mazo de láminas | `cd presentation && npm run pdf` → `dist/deck.pdf`, 14 páginas |
| Cómo se construyó | `.taskops/reports/README.md` — 18 hitos cerrados, cada uno con informe |

---

## Apéndice B — Configuración de proveedores, y por qué

**STT — Soniox `stt-rt-v5`.** `language_hints=["es","en"]`, endpointing
`level=2 / sensitivity=0.3 / max_endpoint_delay_ms ≈ 1000`. El vocabulario de
dominio se pasa por `context=`: Soniox **ignora en silencio** `keyterms`, que es
el parámetro que uno esperaría. `sample_rate=16000` incluso en PSTN. El proveedor
es un slot: la alternativa medida es Deepgram Flux `flux-general-multi` — nunca
`flux-general-en`, que devuelve 400 ante un `language_hint`.

**LLM — Anthropic `claude-haiku-4-5`** con `caching="ephemeral"`. Haiku 4.5 sólo
cachea prefijos de **4096 tokens o más** (por debajo es un no-op silencioso;
Sonnet cachea desde 1024), así que cada prefijo de proyecto —sistema, tools y un
bloque estable de política y FAQ— tiene que superar ese umbral, y los tests
comprueban `prompt_cached_tokens > 0` en el turno 2. Nunca hay marcas de tiempo
ni identificadores por petición en el prompt de sistema, y las tools no se
reordenan: cualquiera de las dos cosas invalida el prefijo entero.

La **generación especulativa está desactivada** por decisión medida: con fin de
turno semántico a ~0,33 s nunca llegó a esconder el ttft de Haiku y sólo gastaba
llamadas. La generación arranca con el fin de turno confirmado.

`gpt-5.4-mini` es la alternativa medida en los evals, no un modelo por defecto.

**TTS — ElevenLabs `eleven_v3_conversational`** (primario) y `eleven_flash_v2_5`
(perfil de latencia), con `sync_alignment=True`. Nunca `eleven_turbo_v2_5`
(obsoleto) ni `eleven_v3` (no es de tiempo real). En una interrupción el plugin
cierra el contexto: no hay que hacer flush. La voz es dato por proyecto, nunca
constante en `core`.

**VAD y turnos.** `inference.VAD(model="silero")` y `inference.TurnDetector()`
(v1-mini, local, CPU). `min_silence_duration >= 0.25` o la sesión levanta
excepción al construirse.

**Chat.** `RoomOptions(audio_input=False, audio_output=False)`; el texto del
agente llega como deltas por `lk.transcription` y el del usuario por `lk.chat`.
El cliente distingue quién habla por `participantInfo.identity`, nunca por id de
pista.
