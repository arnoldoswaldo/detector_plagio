#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import sys

import streamlit as st

# Asegurar que src/ esté en el path para importar codeguard_py
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from codeguard_py import analyze_code_strings, get_sample_codes


# Configuración general de la página

st.set_page_config(
    page_title="CodeGuard-Py | Detector de Plagio ANTLR v4",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    # Encabezado principal
    st.title("🛡️ CodeGuard-Py")
    st.caption(
        "Análisis Sintáctico, Semántica Ligera (Def-Use) y Manipulación Automática "
        "de Código en Python 3 con ANTLR v4"
    )

    # Barra lateral: Parámetros del analizador y modo de demostración rápida
 
    with st.sidebar:
        st.header("⚙️ Configuración")
        threshold = st.slider(
            "Umbral de alerta de plagio (%)",
            min_value=10.0,
            max_value=100.0,
            value=70.0,
            step=5.0,
            help="Porcentaje mínimo de similitud de Jaccard para etiquetar una función como sospechosa.",
        )
        ngram_size = st.slider(
            "Tamaño de ventana (n-gramas)",
            min_value=2,
            max_value=10,
            value=5,
            step=1,
            help="Cantidad de tokens estructurales consecutivos agrupados por shingle.",
        )

        st.divider()
        st.subheader("🧪 Casos de Prueba Rápidos")
        input_mode = st.radio(
            "Fuente de archivos:",
            options=[
                "Subir archivos (.py)",
                "Demo: Plagio Camuflado",
                "Demo: Código Independiente",
            ],
            index=0,
        )
        st.info(
            "Los modos Demo cargan los ejemplos integrados en memoria para "
            "facilitar las pruebas sin necesidad de subir archivos manualmente."
        )

    # Carga de archivos (vía File Uploader o ejemplos integrados)
 
    base_source = None
    suspect_source = None
    base_name = "entrada_original.py"
    suspect_name = "archivo_sospechoso.py"

    samples = get_sample_codes()

    if input_mode == "Subir archivos (.py)":
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            base_file = st.file_uploader(
                "1️⃣ Archivo Base / Referencia (.py)",
                type=["py"],
                key="base_uploader",
            )
            if base_file is not None:
                base_name = base_file.name
                base_source = base_file.getvalue().decode("utf-8", errors="replace")

        with col_up2:
            suspect_file = st.file_uploader(
                "2️⃣ Archivo Sospechoso a Evaluar (.py)",
                type=["py"],
                key="suspect_uploader",
            )
            if suspect_file is not None:
                suspect_name = suspect_file.name
                suspect_source = suspect_file.getvalue().decode("utf-8", errors="replace")

    elif input_mode == "Demo: Plagio Camuflado":
        base_name = "entrada_original.py"
        suspect_name = "entrada_plagio_camuflado.py"
        base_source = samples[base_name]
        suspect_source = samples[suspect_name]
        st.success(
            f"Cargado escenario de demostración: **{base_name}** vs **{suspect_name}**"
        )

    else:
        base_name = "entrada_original.py"
        suspect_name = "entrada_independiente.py"
        base_source = samples[base_name]
        suspect_source = samples[suspect_name]
        st.success(
            f"Cargado escenario de demostración: **{base_name}** vs **{suspect_name}**"
        )

    # Vista previa de entrada antes de ejecutar si falta alguno de los dos archivos
    if base_source is None or suspect_source is None:
        st.warning(
            "Carga tanto el **Archivo Base** como el **Archivo Sospechoso** (o elige un "
            "modo Demo en la barra lateral) para iniciar el análisis con ANTLR v4."
        )
        return

    # Ejecución del motor de análisis y manipulación ANTLR v4
   
    try:
        results = analyze_code_strings(
            base_source=base_source,
            suspect_source=suspect_source,
            base_label=base_name,
            suspect_label=suspect_name,
            threshold=threshold,
            ngram_size=ngram_size,
        )
    except SyntaxError as err:
        st.error(f"❌ Error de sintaxis detectado por ANTLR v4:\n\n{err}")
        return
    except Exception as err:
        st.error(f"❌ Error inesperado durante el procesamiento:\n\n{err}")
        return

    if results["base_functions_count"] == 0 or results["suspect_functions_count"] == 0:
        st.warning(
            "Alguno de los archivos seleccionados no contiene definiciones de funciones (`def`)."
        )
        return

    st.divider()

    # Resumen ejecutivo (Métricas principales)
   
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Funciones Evaluadas", results["suspect_functions_count"])
    m2.metric("Similitud Máxima (Jaccard)", f"{results['max_similarity']:.2f}%")
    m3.metric("Variables Muertas Eliminadas", results["total_dead_vars"])
    verdict_text = "🚨 ALERTA DE PLAGIO" if results["plagiarism_detected"] else "✅ SIN PLAGIO"
    m4.metric("Diagnóstico Global", verdict_text)

  
    # Detalle por función analizada
  
    st.subheader("📊 Resultados por Función")
    for fn in results["function_results"]:
        badge = "🚨 PLAGIO DETECTADO" if fn["is_plagiarism"] else "✅ LIMPIA"
        header = (
            f"{badge} | `{fn['suspect_func']}()` (Línea {fn['start_line']}) "
            f"— Similitud: **{fn['similarity']:.2f}%** con `{fn['matched_func']}()`"
        )
        with st.expander(header, expanded=True):
            c_info, c_tokens = st.columns([1, 2])
            with c_info:
                st.markdown(f"- **Función base coincidente:** `{fn['matched_func']}()`")
                st.markdown(f"- **Índice de Jaccard:** `{fn['similarity']:.2f}%`")
                if fn["dead_variables"]:
                    dead_list = ", ".join(f"`{v}`" for v in fn["dead_variables"])
                    st.markdown(f"- **Código muerto eliminado:** {dead_list}")
                else:
                    st.markdown("- **Código muerto eliminado:** Ninguno")

            with c_tokens:
                st.caption("Huella estructural depurada (tokens normalizados):")
                st.code(" ".join(fn["normalized_tokens"]), language="text")

    # Pestañas de Manipulación Automática y Semántica Ligera
   
    st.subheader("🛠️ Artefactos Generados por TokenStreamRewriter y Semántica Ligera")
    tab_annot, tab_canon, tab_symbols, tab_base = st.tabs(
        [
            "1. Código Anotado (Alertas)",
            "2. Código Canonizado y Depurado",
            "3. Tabla de Símbolos (Def-Use)",
            "4. Código Base de Referencia",
        ]
    )

    with tab_annot:
        col_orig, col_ann = st.columns(2)
        with col_orig:
            st.caption(f"Original recibido (`{suspect_name}`)")
            st.code(results["original_suspect_code"], language="python")
        with col_ann:
            st.caption(f"Manipulado con alertas (`anotado_{suspect_name}`)")
            st.code(results["annotated_code"], language="python")

        st.download_button(
            label=f"⬇️ Descargar anotado_{suspect_name}",
            data=results["annotated_code"],
            file_name=f"anotado_{suspect_name}",
            mime="text/x-python",
        )

    with tab_canon:
        st.caption(
            "Identificadores estandarizados según su rol semántico (`PARAM_i`, `LOCAL_i`), "
            "comentarios omitidos y asignaciones de variables muertas (`usos == 0`) eliminadas."
        )
        st.code(results["canonized_code"], language="python")
        st.download_button(
            label=f"⬇️ Descargar canonizado_{suspect_name}",
            data=results["canonized_code"],
            file_name=f"canonizado_{suspect_name}",
            mime="text/x-python",
        )

    with tab_symbols:
        st.caption(
            "Rastreo local de definiciones y usos (*Def-Use*) por ámbito de función:"
        )
        for fn in results["function_results"]:
            st.markdown(f"**Ámbito: `{fn['suspect_func']}()`**")
            if fn["symbols"]:
                st.dataframe(fn["symbols"], use_container_width=True, hide_index=True)
            else:
                st.write("Sin símbolos locales registrados en esta función.")

    with tab_base:
        st.caption(f"Archivo de referencia (`{base_name}`)")
        st.code(base_source, language="python")


if __name__ == "__main__":
    main()