# Sbayt Server Protocols

Servidores de protocolos e imágenes Docker autónomos. Los clientes externos
crean nodos o publican mensajes; los servidores ofrecen comportamiento genérico
de cada protocolo.

[Read in English](README.md)

## Servidores

| Servidor | Imagen Docker Hub | Puerto interno | Documentación |
| --- | --- | --- | --- |
| OPC UA | `sbayt1/sbayt-opcua-server` | 4840 | [Registro de nodos, escrituras y actividad](services/opcua-server/README.md) |
| MQTT | `sbayt1/sbayt-mqtt-server` | 1883 | [Configuración Mosquitto](services/mqtt-server/README.md) |

Las imágenes comparten versión. La release `v0.1.0` publica `0.1.0` para ambos
servidores; `latest` se actualiza cuando ambas imágenes publicadas superan las
comprobaciones. Se construyen para `linux/amd64` y `linux/arm64`. Las imágenes
estarán disponibles tras la primera publicación correcta.

## Ejecutar las imágenes publicadas

```bash
docker run --rm --name opcua -p 127.0.0.1:4840:4840 sbayt1/sbayt-opcua-server:latest
docker run --rm --name mqtt -p 127.0.0.1:1883:1883 sbayt1/sbayt-mqtt-server:latest
```

El endpoint OPC UA es `opc.tcp://127.0.0.1:4840/signals`. Arranca vacío y acepta
nodos mediante `1:EnsureNodes`. Los clientes escriben valores; la caducidad
configurable y `1:SetSignalActivity` expresan disponibilidad con estados OPC UA.

MQTT escucha en 1883, distribuye los payloads de los publicadores y no persiste
datos en disco. Ambos servidores predeterminados admiten conexiones anónimas
sin cifrado; los ejemplos publican los puertos en la interfaz loopback del host.

## Construcción local

Cada directorio es un contexto Docker completo:

```bash
docker build -t sbayt-opcua-server:local services/opcua-server
docker build -t sbayt-mqtt-server:local services/mqtt-server
```

Antes de publicar, utiliza esos nombres locales en los comandos de ejecución.
Cada servicio conserva sus contratos y versiones de dependencias.

## Desarrollo y validación

Requiere Python 3.14 y uv para desarrollar OPC UA y probar las imágenes.
Todas las dependencias Python proceden de PyPI público. El proyecto raíz contiene
las herramientas independientes para probar imágenes. Solo las pruebas OPC UA
instalan su cliente; MQTT utiliza los clientes incluidos en la imagen del broker.

```bash
uv sync --locked
uv sync --project services/opcua-server --locked --all-groups
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --project services/opcua-server mypy --config-file services/opcua-server/pyproject.toml services/opcua-server/src
uv run --project services/opcua-server pytest services/opcua-server/tests
```

Después de construir las imágenes:

```bash
SERVER_PROTOCOL=opcua SERVER_IMAGE=sbayt-opcua-server:local \
  uv run --locked --group opcua pytest tests/test_opcua.py
SERVER_PROTOCOL=mqtt SERVER_IMAGE=sbayt-mqtt-server:local \
  uv run --locked --group mqtt pytest tests/test_mqtt.py
```

Las pruebas comprueban salud, registro/escritura/caducidad/reinicio OPC UA y
entrega MQTT sin retención. Usan contenedores temporales y puertos aleatorios;
al terminar retiran sus contenedores y volúmenes anónimos. `SERVER_PLATFORM`
permite seleccionar otra arquitectura cuando Docker puede ejecutarla.
Los nombres de pruebas siguen `test_given_when_then`.

## Añadir un servidor

1. Crear un directorio autónomo bajo `services/`, con Dockerfile, configuración,
   healthcheck, documentación y las pruebas de su código.
2. Añadir nombre, contexto, imagen y puerto a `services.json`. El catálogo se usa
   en CI, publicación de versiones y promoción de `latest`.
3. Añadir `tests/test_<nombre>.py` y un grupo de dependencias con el mismo nombre
   en el `pyproject.toml` raíz (vacío si no necesita otro cliente). La fixture común
   comprueba la salud del contenedor. Añadir comprobaciones de código a CI si
   requiere otra tecnología.
4. Actualizar ambos README y crear su repositorio público de Docker Hub.

Los modelos de negocio, las transformaciones específicas de cada cliente y la
gestión de despliegues corresponden a los consumidores del repositorio.

## Publicación

CI valida el código y las imágenes en PR y `master`. Publicar una release estable
como `v0.1.0` repite CI, publica las dos imágenes versionadas, comprueba su descarga
anónima y ambas arquitecturas, y promueve los manifiestos verificados a `latest`.
Las comprobaciones de PR no reciben credenciales de publicación.

Los pasos manuales están en [la guía de publicación](docs/publishing.md).
El tag de release determina la versión conjunta de las imágenes Docker. El
paquete Python del servidor OPC UA no se publica por separado.

## Licencia

[MIT](LICENSE) para el código y configuración de este repositorio. Las imágenes
base y dependencias mantienen sus propias licencias.
