/**
 * registro.js
 * -----------
 * Lógica del formulario de registro manual de ingresantes:
 *  - Vista previa de la foto seleccionada.
 *  - Envío del formulario (multipart/form-data) al endpoint
 *    POST /api/estudiantes/registrar y muestra del resultado.
 */

(function () {
    "use strict";

    const form = document.getElementById("form-registro");
    const inputFoto = document.getElementById("foto");
    const preview = document.getElementById("preview");
    const fotoLabel = document.getElementById("foto-label");
    const btnGuardar = document.getElementById("btn-guardar");
    const mensaje = document.getElementById("mensaje");

    // --- Vista previa de la foto ---------------------------------------------------
    inputFoto.addEventListener("change", () => {
        const archivo = inputFoto.files && inputFoto.files[0];
        if (!archivo) return;
        fotoLabel.textContent = archivo.name;
        const lector = new FileReader();
        lector.onload = (e) => {
            preview.src = e.target.result;
            preview.classList.remove("hidden");
        };
        lector.readAsDataURL(archivo);
    });

    // --- Envío del formulario ----------------------------------------------------------
    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        if (!inputFoto.files || !inputFoto.files[0]) {
            mostrarMensaje("error", "Debe seleccionar una foto de perfil.");
            return;
        }

        btnGuardar.disabled = true;
        mostrarMensaje("info", "Procesando rostro y guardando registro...");

        try {
            const datosFormulario = new FormData(form);
            const respuesta = await fetch("/api/estudiantes/registrar", {
                method: "POST",
                body: datosFormulario,
            });
            const datos = await respuesta.json();

            if (respuesta.ok && datos.ok) {
                mostrarMensaje("exito", datos.mensaje);
                form.reset();
                preview.classList.add("hidden");
                fotoLabel.textContent =
                    "Haz clic para seleccionar la foto (rostro único y frontal)";
            } else {
                mostrarMensaje("error", datos.mensaje || "No se pudo completar el registro.");
            }
        } catch (err) {
            mostrarMensaje("error", "Error de red al comunicarse con el servidor.");
        } finally {
            btnGuardar.disabled = false;
        }
    });

    // --- Utilidad de UI ------------------------------------------------------------------
    function mostrarMensaje(tipo, texto) {
        const estilos = {
            exito: "bg-emerald-50 border-emerald-300 text-emerald-800",
            error: "bg-rose-50 border-rose-300 text-rose-800",
            info: "bg-indigo-50 border-indigo-300 text-indigo-800",
        };
        mensaje.className =
            "mt-5 border rounded-xl px-4 py-3 text-sm " + (estilos[tipo] || estilos.info);
        mensaje.textContent = texto;
        mensaje.classList.remove("hidden");
    }
})();
