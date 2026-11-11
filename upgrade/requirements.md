# Requisitos: cuentas de prueba (gratis) y producción (pago)

Para correr el pipeline contra Google hacen falta cuentas, credenciales y datos de producto. Google ofrece cuentas de prueba que permiten validar la integración completa sin costo. Las campañas de Google Ads quedaron fuera de alcance, porque mostrar anuncios y medir su rendimiento cuesta dinero.

## Tabla de requisitos

| Requisito | Gratis (cuenta de prueba) | Pago (producción) |
|---|---|---|
| Cuenta de Google Merchant Center | Cuenta de prueba, aislada de los datos reales; no muestra productos a nadie | Cuenta real verificada (dominio y datos del negocio) |
| Credenciales | Cuenta de servicio (evita los tokens OAuth manuales) | OAuth2 o cuenta de servicio, más Merchant ID |
| Proyecto de Google Cloud | Necesario (gratis) para habilitar las APIs | Necesario |
| Datos de producto | Sirven datos inventados (precios, GTIN). No se publica nada | **Datos reales obligatorios**: GTIN válido si el producto lo tiene, precio real, link activo, stock |
| Productos visibles | No: solo se ven dentro de Merchant Center | Sí: en Google Shopping, como listados gratuitos |
| Qué se puede validar | Que el código sube el producto y lee si Google lo aprobó | Lo mismo, con datos reales y productos visibles |

## Notas

- **Desarrollo gratis completo:** una cuenta de prueba de Merchant Center y un proyecto de Google Cloud alcanzan para validar el flujo de punta a punta (URL de la foto → atributos → feed → publicación → estado) sin gasto.
- **Límite del modo gratis:** las cuentas de prueba no publican nada. Validan que la integración funciona, no el posicionamiento.
- **Fuera de alcance:** campañas de Google Ads. Las cuentas de prueba de Google Ads no muestran anuncios ni dan métricas, y medir de verdad requiere pagar los clics.
- **Merchant API:** la Content API for Shopping se dio de baja el 2026-08-18. El pipeline apunta a la Merchant API, que tiene sus propias cuentas de prueba.
- **Estado del código:** las llamadas a Merchant API son reales y se probaron contra una cuenta de prueba ([`MERCHANT_SETUP.md`](MERCHANT_SETUP.md)).

## Orden recomendado para armar el entorno gratis

1. Crear un proyecto en Google Cloud Console.
2. Habilitar **Merchant API**.
3. Crear una **cuenta de prueba** en Merchant Center.
4. Configurar una **cuenta de servicio** y bajar su clave JSON.
5. Guardar las credenciales fuera del repo (variables de entorno o un gestor de secretos) y nunca commitear claves.

Variables de entorno que lee `positioner/publishing/` (`credential_loader.py` las tres primeras, `environment.py` la cuarta):

```bash
GOOGLE_SERVICE_ACCOUNT_PATH=/ruta/a/la/clave.json
MERCHANT_ID=123456789
MERCHANT_DATA_SOURCE_ID=987654   # fuente de datos de tipo API (para subir)
MERCHANT_ENV=test          # o "production"
```

## Fuentes (consultadas el 2026-10-26)

- [Merchant API: cuentas de prueba](https://developers.google.com/merchant/api/guides/accounts/test-accounts)
- [Content API for Shopping: baja](https://developers.google.com/shopping-content/guides/sunset)

Precios y políticas pueden cambiar: antes de pasar a producción hay que contrastarlos con la documentación oficial de Google.
