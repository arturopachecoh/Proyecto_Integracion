"""Cliente del SOAP de facturacion: emitir, pagar, listar facturas y saldo.

Solo traduce: arma el XML, lo envia y devuelve diccionarios. Si el servicio
responde un Fault, lanza SoapError con su codigo (ej. DUPLICATE_OPERATION).
Que hacer con cada error lo decide quien llama."""
import httpx
from defusedxml.ElementTree import fromstring

from app.config import FARMA_API_KEY, FARMA_BASE_URL, FARMA_GROUP

URL = f"{FARMA_BASE_URL}/soap/billing"

# Ojo: sin Type="...#PasswordText" el servicio responde 401 aunque la clave
# este bien (Zeep lo agrega solo; la documentacion del curso no lo dice).
SOBRE = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:bil="http://billing.tallerdeintegracion.cl">
<soapenv:Header>
 <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
  <wsse:UsernameToken>
   <wsse:Username>{usuario}</wsse:Username>
   <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">{clave}</wsse:Password>
  </wsse:UsernameToken>
 </wsse:Security>
</soapenv:Header>
<soapenv:Body><bil:{operacion}Request>{cuerpo}</bil:{operacion}Request></soapenv:Body>
</soapenv:Envelope>"""


class SoapError(Exception):
    def __init__(self, codigo, mensaje):
        super().__init__(f"{codigo}: {mensaje}")
        self.codigo = codigo


def _llamar(operacion, cuerpo=""):
    xml = SOBRE.format(usuario=FARMA_GROUP, clave=FARMA_API_KEY,
                       operacion=operacion, cuerpo=cuerpo)
    r = httpx.post(URL, content=xml.encode(), timeout=30,
                   headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": operacion})
    try:
        raiz = fromstring(r.content)
    except Exception:
        raise SoapError(f"HTTP {r.status_code}", r.text[:200])  # ej. un 502 en HTML
    if r.status_code != 200:
        campos = {e.tag.split("}")[-1]: e.text for e in raiz.iter()}
        raise SoapError(campos.get("faultcode") or campos.get("Value") or f"HTTP {r.status_code}",
                        campos.get("faultstring") or campos.get("Text"))
    return raiz


def _facturas_en(raiz):
    """Cada <BillingDetails> como dict, sin namespaces y con montos como float."""
    lista = []
    for el in raiz.iter():
        if el.tag.endswith("BillingDetails"):
            f = {h.tag.split("}")[-1]: h.text for h in el}
            for k in ("price", "interest", "totalPrice"):
                f[k] = float(f.get(k) or 0)
            lista.append(f)
    return lista


def emitir(oc_id):
    return _facturas_en(_llamar("emitInvoice", f"<bil:order_id>{oc_id}</bil:order_id>"))[0]


def pagar(factura_id):
    return _facturas_en(_llamar("payInvoice", f"<bil:invoice_id>{factura_id}</bil:invoice_id>"))[0]


def facturas(estado, lado, desde, hasta):
    """estado: pending|paid. lado: client (las que pagamos) | supplier (las que emitimos).
    desde/hasta: datetime en UTC, maximo 3 dias entre ambos."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return _facturas_en(_llamar("getInvoices",
        f"<bil:status>{estado}</bil:status><bil:side>{lado}</bil:side>"
        f"<bil:fromDate>{desde.strftime(fmt)}</bil:fromDate><bil:toDate>{hasta.strftime(fmt)}</bil:toDate>"))


def saldo():
    raiz = _llamar("getBankStatement")
    return float(next(e.text for e in raiz.iter() if e.tag.endswith("balance")))
