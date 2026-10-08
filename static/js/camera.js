/**
 * camera.js
 * ---------
 * Lógica del panel de marcación del dashboard (solo cámara en vivo):
 *  - Solicita acceso a la cámara del punto de control.
 *  - Captura el fotograma actual del video y lo envía al endpoint
 *    POST /api/acceso/marcar como imagen base64 (data URL).
 */

(function () {
    "use strict";

    // --- Elementos del DOM -------------------------------------------------
    const video = document.getElementById("video");
    const canvas = document.getElementById("canvas-captura");
    const overlayCamara = document.getElementById("overlay-camara");

    const btnIngreso = document.getElementById("btn-ingreso");
    const btnSalida = document.getElementById("btn-salida");
    const btnAuto = document.getElementById("btn-auto");

    const resultado = document.getElementById("resultado");

    let streamActivo = null;

    // --- Gestión de la cámara ----------------------------------------------
    async function iniciarCamara() {
        try {
            streamActivo = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 640 }, height: { ideal: 480 } },
                audio: false,
            });
            video.srcObject = streamActivo;
            overlayCamara.classList.add("hidden");
            overlayCamara.classList.remove("flex");
        } catch (err) {
            overlayCamara.classList.remove("hidden");
            overlayCamara.classList.add("flex");
            overlayCamara.textContent =
                "No se pudo acceder a la cámara. Verifique los permisos del navegador.";
        }
    }

    function camaraLista() {
        return Boolean(streamActivo) && video.videoWidth > 0;
    }

    // --- Captura del fotograma actual en base64 ----------------------------
    function capturarFotogramaBase64() {
        if (!camaraLista()) {
            mostrarMensaje(
                "error",
                "La cámara no está lista todavía. Espere unos segundos e inténtelo de nuevo."
            );
            return null;
        }
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.92);
    }

    // --- Envío de la marcación ---------------------------------------------
    async function marcar(tipoEvento) {
        const imagen = capturarFotogramaBase64();
        if (!imagen) return;

        setBotonesHabilitados(false);
        mostrarMensaje("info", "Procesando rostro, por favor espere...");

        try {
            const respuesta = await fetch("/api/acceso/marcar", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    imagen_base64: imagen,
                    tipo_evento: tipoEvento, // null -> alternancia automática
                }),
            });
            const datos = await respuesta.json();

            if (respuesta.ok && datos.ok) {
                const est = datos.estudiante || {};
                mostrarMensaje(
                    "exito",
                    `<strong>${datos.tipo_evento}</strong> registrado:<br>` +
                        `${est.nombres || ""} ${est.apellidos || ""} ` +
                        `(${est.codigo_estudiante || ""})<br>` +
                        `<span class="text-xs">Similitud: ${datos.similitud}</span>`
                );
                // Refrescar la tabla tras un breve instante.
                setTimeout(() => window.location.reload(), 1800);
            } else {
                mostrarMensaje("error", datos.mensaje || "No se pudo registrar el acceso.");
            }
        } catch (err) {
            mostrarMensaje("error", "Error de red al comunicarse con el servidor.");
        } finally {
            setBotonesHabilitados(true);
        }
    }

    btnIngreso.addEventListener("click", () => marcar("INGRESO"));
    btnSalida.addEventListener("click", () => marcar("SALIDA"));
    btnAuto.addEventListener("click", () => marcar(null));

    // --- Utilidades de UI ---------------------------------------------------
    function setBotonesHabilitados(habilitado) {
        [btnIngreso, btnSalida, btnAuto].forEach((b) => (b.disabled = !habilitado));
    }

    function mostrarMensaje(tipo, html) {
        const estilos = {
            exito: "bg-emerald-50 border-emerald-300 text-emerald-800",
            error: "bg-rose-50 border-rose-300 text-rose-800",
            info: "bg-indigo-50 border-indigo-300 text-indigo-800",
        };
        resultado.className =
            "mt-5 border rounded-xl px-4 py-3 text-sm " + (estilos[tipo] || estilos.info);
        resultado.innerHTML = html;
        resultado.classList.remove("hidden");
    }

    // --- Arranque -----------------------------------------------------------
    iniciarCamara();
})();
