"""Jerarquía de excepciones propias del proyecto lectorPlacas."""

from __future__ import annotations


class LectorPlacasError(Exception):
    """Raíz de todas las excepciones del proyecto."""


# --- Dominio ---
class DomainError(LectorPlacasError):
    """Error de las reglas del dominio."""


class InvalidBoundingBoxError(DomainError):
    """Caja delimitadora inválida."""


class InvalidConfidenceError(DomainError):
    """Valor de confianza fuera del intervalo [0, 1]."""


class InvalidPlateTextError(DomainError):
    """Texto de placa que no cumple el formato esperado."""


class InvalidEntityError(DomainError):
    """Entidad del dominio con atributos incoherentes."""


class PlateFormatCatalogError(DomainError):
    """Formato de placa o catálogo de formatos inválido."""


class ConsolidationError(DomainError):
    """Error al consolidar las lecturas de un track."""


# --- Aplicación / infraestructura / adaptadores ---
class ConfigurationError(LectorPlacasError):
    """Configuración ausente o inválida."""


class InputValidationError(LectorPlacasError):
    """Entrada del usuario que no supera la validación."""


class UnsafePathError(InputValidationError):
    """Ruta fuera de los directorios permitidos."""


class VideoSourceError(LectorPlacasError):
    """Error al abrir, decodificar o recorrer un video."""


class ModelIntegrityError(LectorPlacasError):
    """Modelo con hash o tamaño distinto al esperado."""


class ModelLoadError(LectorPlacasError):
    """Error al cargar un modelo en memoria."""


class ModelFetchError(LectorPlacasError):
    """Error al descargar o instalar un modelo."""


class InferenceError(LectorPlacasError):
    """Error durante la inferencia de un modelo."""


class TrackingError(LectorPlacasError):
    """Error durante el seguimiento de vehículos."""


class RepositoryError(LectorPlacasError):
    """Error al acceder a la base de datos."""


class SightingNotFoundError(RepositoryError):
    """Avistamiento inexistente en la base de datos."""


class CropStoreError(LectorPlacasError):
    """Error al guardar, leer o borrar recortes."""


class CropNotFoundError(CropStoreError):
    """Recorte inexistente en el almacén."""


class ExportError(LectorPlacasError):
    """Error al exportar avistamientos."""


class EncryptionError(LectorPlacasError):
    """Error al cifrar o descifrar datos."""


class KeyUnavailableError(LectorPlacasError):
    """Clave maestra no disponible en el llavero del sistema."""


class NetworkAccessError(LectorPlacasError):
    """Intento de acceso a la red bloqueado."""


class ReviewError(LectorPlacasError):
    """Error durante la revisión humana de avistamientos."""


class EvaluationError(LectorPlacasError):
    """Error al calcular métricas de evaluación."""


class DatasetError(LectorPlacasError):
    """Error al preparar conjuntos de datos."""
