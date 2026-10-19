# Publicación en GitHub y Docker Hub

## Preparación manual de GitHub

1. Crear `Steel-Develop/sbayt-server-protocols` como repositorio **Public** y vacío,
   sin generar README, licencia ni `.gitignore`. Esos archivos se incluyen aquí.
2. Revisar el contenido preparado y crear el primer commit local. El remoto `origin`
   apunta al repositorio público. Subir la rama inicial:

   ```bash
   git push -u origin master
   ```

3. Comprobar que `master` es la rama predeterminada y que GitHub Actions está
   habilitado. La política de la organización debe permitir las acciones usadas
   por los workflows: `actions/*`, `astral-sh/setup-uv` y `docker/*`.
4. En **Settings → Secrets and variables → Actions → New repository secret**,
   configurar `DOCKERHUB_USERNAME` y `DOCKERHUB_TOKEN`. El usuario debe poder
   publicar en el namespace `sbayt1` y el token necesita permisos de escritura
   para las dos imágenes. Si ya existen como secretos de organización, conceder
   acceso a este repositorio desde la configuración de `Steel-Develop`.
5. Esperar a que **CI** termine correctamente en `master`.

Los secretos se utilizan solamente en los jobs que publican imágenes o actualizan
`latest`. Los jobs de verificación descargan las imágenes sin autenticación.

## Preparación manual de Docker Hub

Crear como públicos estos repositorios en el namespace `sbayt1`:

- `sbayt-opcua-server`
- `sbayt-mqtt-server`

## Primera publicación

1. En GitHub, entrar en **Releases → Draft a new release**.
2. Crear el tag **`v0.1.0`**, seleccionando `master` como destino.
3. Añadir las notas y pulsar **Publish release**, sin marcar prerelease.
4. En **Actions → Publish**, comprobar los resultados:
   - Validación del tag y de que el commit pertenece al historial de `master`.
   - CI de código y contenedores para ambas arquitecturas.
   - Publicación de las dos imágenes con etiqueta `0.1.0`.
   - Descarga anónima y pruebas de protocolo para `amd64` y `arm64`.
   - Promoción de ambos manifiestos verificados a `latest`.

Crear únicamente un tag o guardar un borrador de release no publica imágenes.
Los tags estables siguen `vX.Y.Z`; las siguientes releases comparten versión entre
servidores. Los tags de las imágenes omiten la `v`.

Si falla una comprobación anterior a la promoción, `latest` permanece intacto.
Puede haber imágenes versionadas de un intento incompleto. Consulta el job
fallido antes de reintentarlo desde Actions.

## Comprobación después de publicar

Desde un cliente Docker sin credenciales de publicación:

```bash
docker pull sbayt1/sbayt-opcua-server:0.1.0
docker pull sbayt1/sbayt-mqtt-server:0.1.0
docker buildx imagetools inspect sbayt1/sbayt-opcua-server:0.1.0
docker buildx imagetools inspect sbayt1/sbayt-mqtt-server:0.1.0
```

Los manifiestos deben incluir `linux/amd64` y `linux/arm64`. Los consumidores
pueden usar el tag de versión o `latest` según sus necesidades.

## Referencias

- [Crear un repositorio](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository).
- [Secretos de GitHub Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).
- [Publicar imágenes Docker](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images).
- [Administrar releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
