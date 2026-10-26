"""Retiro de lote (recall) emitido por Farma Central.

webhook         recibe el aviso (POST /api/recalls) y expone el registro para /recalls
registro        unico modulo que escribe retiros, retiro_unidades y retiro_notificaciones
investigacion   que afecta el retiro (solo lectura de custodia)
procesamiento   reporte, notificaciones y cuarentena (lo corre el worker)
"""
