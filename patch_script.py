import os

with open("script.py", "r", encoding="utf-8") as f:
    content = f.read()

# ADD analizar_por_persona
part_analisis = """
def analizar_por_persona(registros: list[dict], config: dict) -> dict:
    \"\"\"
    Analiza los registros de todas las personas, organizados por persona.
    \"\"\"
    h_leve   = datetime.strptime(config["tardanza_leve"],   "%H:%M").time()
    h_severa = datetime.strptime(config["tardanza_severa"], "%H:%M").time()
    max_almuerzo_min = config.get("max_almuerzo_min", 60)

    # Agrupar por persona y luego por fecha
    por_persona_fecha = defaultdict(lambda: defaultdict(list))
    for r in registros:
        por_persona_fecha[r["nombre"]][r["fecha"]].append(r)

    resultado = {}

    for nombre, por_fecha in por_persona_fecha.items():
        dias_list = []
        resumen = {
            "total_dias": 0,
            "tardanza_leve": 0,
            "tardanza_severa": 0,
            "almuerzo_largo": 0,
            "incompletos": 0
        }

        for fecha, marcaciones in sorted(por_fecha.items()):
            marcaciones.sort(key=lambda x: x["datetime"])
            
            dia_info = {
                "fecha": fecha,
                "llegada": None,
                "salida": None,
                "almuerzo_duracion": None,
                "almuerzo_exceso": None,
                "observaciones": [],
                "estado": "ok"
            }
            
            n = len(marcaciones)
            resumen["total_dias"] += 1

            if n < 2 or n not in (2, 4):
                dia_info["estado"] = "incompleto"
                dia_info["observaciones"].append(f"Registros anómalos ({n})")
                resumen["incompletos"] += 1
                
                # Intentamos sacar llegada de todas formas
                if marcaciones[0]["tipo"] == "Entrada":
                     dia_info["llegada"] = marcaciones[0]["hora"].strftime("%H:%M")
                # Intentamos sacar salida si hay varios
                if len(marcaciones) > 1 and marcaciones[-1]["tipo"] == "Salida":
                     dia_info["salida"] = marcaciones[-1]["hora"].strftime("%H:%M")

            else:
                primera = marcaciones[0]
                ultima = marcaciones[-1]
                if primera["tipo"] == "Entrada":
                    dia_info["llegada"] = primera["hora"].strftime("%H:%M")
                    if primera["hora"] > h_severa:
                        dia_info["estado"] = "severa"
                        dia_info["observaciones"].append("Tardanza severa")
                        resumen["tardanza_severa"] += 1
                    elif primera["hora"] > h_leve:
                        if dia_info["estado"] == "ok":
                            dia_info["estado"] = "leve"
                        dia_info["observaciones"].append("Tardanza leve")
                        resumen["tardanza_leve"] += 1
                
                if ultima["tipo"] == "Salida":
                    dia_info["salida"] = ultima["hora"].strftime("%H:%M")

                # Analizar almuerzo si hay >= 4 marcaciones
                if n >= 4:
                    salida_almuerzo = None
                    for i, m in enumerate(marcaciones):
                        if m["tipo"] == "Salida" and i > 0:
                            salida_almuerzo = m
                            for j in range(i + 1, len(marcaciones)):
                                if marcaciones[j]["tipo"] == "Entrada":
                                    entrada_almuerzo = marcaciones[j]
                                    duracion = (entrada_almuerzo["datetime"] - salida_almuerzo["datetime"]).total_seconds() / 60
                                    dia_info["almuerzo_duracion"] = round(duracion)
                                    if duracion > max_almuerzo_min:
                                        exceso = round(duracion - max_almuerzo_min)
                                        dia_info["almuerzo_exceso"] = exceso
                                        if dia_info["estado"] == "ok":
                                            dia_info["estado"] = "leve"
                                        dia_info["observaciones"].append(f"Exceso almuerzo (+{exceso}m)")
                                        resumen["almuerzo_largo"] += 1
                                    break
                            break

            dias_list.append(dia_info)

        if dias_list:
            resultado[nombre] = {
                "dias": dias_list,
                "resumen": resumen
            }

    return resultado

def _minutos_diferencia(hora_limite, hora_real) -> int:
"""

content = content.replace("def _minutos_diferencia(hora_limite, hora_real) -> int:", part_analisis)

# ADD generar_pdf_persona
part_pdf = """def generar_pdf_persona(
    ruta_salida: str,
    analisis_persona: dict,
    config: dict,
    nombre_archivo_origen: str,
):
    doc = SimpleDocTemplate(
        ruta_salida,
        pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Reporte Biométrico por Persona",
        author="Sistema de Control de Asistencia",
    )

    styles  = getSampleStyleSheet()
    story   = []
    st = _crear_estilos(styles)

    # ── Portada ───────────────────────────────────────────────────────
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("REPORTE DE ASISTENCIA (POR PERSONA)", st["titulo"]))
    story.append(Paragraph("Control Biométrico de Personal", st["subtitulo"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_HEADER))
    story.append(Spacer(1, 1*cm))

    datos_portada = [
        ["Archivo origen:",  os.path.basename(nombre_archivo_origen)],
        ["Generado el:",     datetime.now().strftime("%d/%m/%Y %H:%M")],
        ["Personas total:",  str(len(analisis_persona))],
        ["Tardanza leve desde:", config.get("tardanza_leve", "")],
        ["Tardanza severa desde:", config.get("tardanza_severa", "")],
        ["Almuerzo máximo:", f"{config.get('max_almuerzo_min', '')} minutos"],
    ]
    t_portada = Table(datos_portada, colWidths=[6*cm, 10*cm])
    t_portada.setStyle(TableStyle([
        ("FONTNAME",    (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",    (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("TEXTCOLOR",   (0,0), (0,-1), COLOR_SUBHEADER),
        ("TEXTCOLOR",   (1,0), (1,-1), COLOR_TEXTO),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("TOPPADDING",  (0,0),(-1,-1), 6),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.white, COLOR_TABLA_ALT]),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(t_portada)
    story.append(PageBreak())

    # ── Resumen General ───────────────────────────────────────────────
    story.append(Paragraph("RESUMEN GENERAL", st["dia_titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
    story.append(Spacer(1, 0.5*cm))

    encabezado_resumen = ["Persona", "Días", "Tard. Leves", "Tard. Severas", "Exceso Almuerzo", "Incompletos"]
    filas_resumen = [encabezado_resumen]
    
    for nombre in sorted(analisis_persona.keys()):
        r = analisis_persona[nombre]["resumen"]
        filas_resumen.append([
            nombre,
            str(r["total_dias"]),
            str(r["tardanza_leve"]),
            str(r["tardanza_severa"]),
            str(r["almuerzo_largo"]),
            str(r["incompletos"]),
        ])
    
    t_resumen = Table(filas_resumen, colWidths=[5*cm, 2*cm, 2.5*cm, 2.8*cm, 3.2*cm, 2.5*cm])
    t_resumen.setStyle(_estilo_tabla_datos(len(filas_resumen)))
    story.append(t_resumen)

    # ── Sección por persona ───────────────────────────────────────────
    for nombre in sorted(analisis_persona.keys()):
        story.append(PageBreak())
        story.append(Paragraph(f"👤 {nombre}", st["dia_titulo"]))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_SUBHEADER))
        story.append(Spacer(1, 0.3*cm))
        
        r = analisis_persona[nombre]["resumen"]
        story.append(Paragraph(
            f"<b>{r['total_dias']}</b> días registrados  |  "
            f"<b>{r['tardanza_leve']}</b> tard. leves  |  "
            f"<b>{r['tardanza_severa']}</b> tard. severas  |  "
            f"<b>{r['almuerzo_largo']}</b> exc. almuerzo  |  "
            f"<b>{r['incompletos']}</b> anómalos",
            st["pequeño"]
        ))
        story.append(Spacer(1, 0.4*cm))

        datos = analisis_persona[nombre]["dias"]
        if not datos:
            story.append(Paragraph("Sin registros.", st["normal"]))
            continue

        encabezado_dias = ["Día", "Llegada", "Salida", "Dur. Almuerzo", "Observaciones"]
        filas_dias = [encabezado_dias]
        
        row_colors = []
        for i, d in enumerate(datos, 1):
            fecha_str = d["fecha"].strftime("%d/%m/%Y")
            llegada = d["llegada"] or "—"
            salida = d["salida"] or "—"
            dur_almuerzo = f"{d['almuerzo_duracion']} min" if d["almuerzo_duracion"] else "—"
            obs = ", ".join(d["observaciones"]) if d["observaciones"] else "✓ Ok"
            
            filas_dias.append([fecha_str, llegada, salida, dur_almuerzo, obs])
            
            estado = d["estado"]
            if estado == "ok":
                row_colors.append(COLOR_OK)
            elif estado == "leve":
                row_colors.append(COLOR_WARN)
            elif estado == "severa":
                row_colors.append(COLOR_ERROR)
            elif estado == "incompleto":
                row_colors.append(COLOR_TABLA_ALT)
            else:
                row_colors.append(colors.white)

        t_dias = Table(filas_dias, colWidths=[2.5*cm, 2.2*cm, 2.2*cm, 3*cm, 7.5*cm])
        
        estilos_base = [
            ("BACKGROUND",    (0,0), (-1,0), COLOR_HEADER),
            ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,0), 8.5),
            ("ALIGN",         (0,0), (-1,0), "CENTER"),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
            ("FONTSIZE",      (0,1), (-1,-1), 8.5),
            ("TEXTCOLOR",     (0,1), (-1,-1), COLOR_TEXTO),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 6),
            ("RIGHTPADDING",  (0,0), (-1,-1), 6),
            ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ]
        
        for i, color_ in enumerate(row_colors, 1):
            estilos_base.append(("BACKGROUND", (0,i), (-1,i), color_))
            
        t_dias.setStyle(TableStyle(estilos_base))
        story.append(t_dias)

    doc.build(story, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    print(f"\\n✅ Reporte por persona generado: {ruta_salida}\\n")

def _crear_estilos(base):
"""

content = content.replace("def _crear_estilos(base):", part_pdf)


# CLI arguments
import re

content = content.replace('parser.add_argument("archivo",\n        help="Archivo biométrico (.xls, .xlsx o .csv)")', '''parser.add_argument("archivo",
        help="Archivo biométrico (.xls, .xlsx o .csv)")
    parser.add_argument("--modo", choices=["general", "persona"], default="general",
        help="Modo del reporte (default: general)")
    parser.add_argument("--persona", metavar="NOMBRE",
        help="Si el modo es 'persona', generar reporte solo para esta persona.")''')

main_logic = """
    # ── Agrupar por fecha ──────────────────────────────────────────────
    por_fecha = defaultdict(list)
    for r in registros:
        por_fecha[r["fecha"]].append(r)

    # Filtrar por día si se especificó
    if args.fecha:
        por_fecha = {
            fecha: regs for fecha, regs in por_fecha.items()
            if fecha.day == args.fecha
        }
        if not por_fecha:
            print(f"❌ No se encontraron registros para el día {args.fecha}")
            sys.exit(1)

    # ── Analizar ───────────────────────────────────────────────────────
    print(f"\\n📊 Analizando {len(por_fecha)} día(s)...")
    analisis_por_dia = {}
    for fecha, regs in sorted(por_fecha.items()):
        analisis_por_dia[fecha] = analizar_dia(
            regs,
            config["tardanza_leve"],
            config["tardanza_severa"],
            config["max_almuerzo_min"],
        )
        r = analisis_por_dia[fecha]["resumen"]
        print(f"   {fecha.strftime('%d/%m/%Y')}  →  "
              f"{r['total_personas']} personas, "
              f"{r['tardanza_leve']} tard.leves, "
              f"{r['tardanza_severa']} tard.severas, "
              f"{r['almuerzo_largo']} excesos almuerzo")

    # ── Generar PDF ────────────────────────────────────────────────────
    if args.salida:
        ruta_pdf = args.salida
    else:
        base = os.path.splitext(os.path.basename(args.archivo))[0]
        ruta_pdf = f"reporte_{base}.pdf"

    print(f"\\n📄 Generando PDF: {ruta_pdf}")
    generar_pdf(
        ruta_pdf,
        analisis_por_dia,
        log_dup,
        config,
        args.archivo,
    )
"""

new_main_logic = """
    if args.modo == "persona":
        print(f"\\n📊 Analizando registros por persona...")
        analisis_persona = analizar_por_persona(registros, config)
        
        if args.persona:
            if args.persona in analisis_persona:
                analisis_persona = {args.persona: analisis_persona[args.persona]}
            else:
                print(f"❌ No se encontraron registros para la persona '{args.persona}'")
                sys.exit(1)
        
        if args.salida:
            ruta_pdf = args.salida
        else:
            base = os.path.splitext(os.path.basename(args.archivo))[0]
            persona_suffix = f"_{args.persona.replace(' ', '_')}" if args.persona else ""
            ruta_pdf = f"reporte_persona_{base}{persona_suffix}.pdf"

        print(f"\\n📄 Generando PDF por persona: {ruta_pdf}")
        generar_pdf_persona(
            ruta_pdf,
            analisis_persona,
            config,
            args.archivo,
        )
    else:
        # ── Agrupar por fecha ──────────────────────────────────────────────
        por_fecha = defaultdict(list)
        for r in registros:
            por_fecha[r["fecha"]].append(r)

        # Filtrar por día si se especificó
        if args.fecha:
            por_fecha = {
                fecha: regs for fecha, regs in por_fecha.items()
                if fecha.day == args.fecha
            }
            if not por_fecha:
                print(f"❌ No se encontraron registros para el día {args.fecha}")
                sys.exit(1)

        # ── Analizar ───────────────────────────────────────────────────────
        print(f"\\n📊 Analizando {len(por_fecha)} día(s)...")
        analisis_por_dia = {}
        for fecha, regs in sorted(por_fecha.items()):
            analisis_por_dia[fecha] = analizar_dia(
                regs,
                config["tardanza_leve"],
                config["tardanza_severa"],
                config["max_almuerzo_min"],
            )
            r = analisis_por_dia[fecha]["resumen"]
            print(f"   {fecha.strftime('%d/%m/%Y')}  →  "
                  f"{r['total_personas']} personas, "
                  f"{r['tardanza_leve']} tard.leves, "
                  f"{r['tardanza_severa']} tard.severas, "
                  f"{r['almuerzo_largo']} excesos almuerzo")

        # ── Generar PDF ────────────────────────────────────────────────────
        if args.salida:
            ruta_pdf = args.salida
        else:
            base = os.path.splitext(os.path.basename(args.archivo))[0]
            ruta_pdf = f"reporte_{base}.pdf"

        print(f"\\n📄 Generando PDF: {ruta_pdf}")
        generar_pdf(
            ruta_pdf,
            analisis_por_dia,
            log_dup,
            config,
            args.archivo,
        )
"""

content = content.replace(main_logic, new_main_logic)

with open("script.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied")
