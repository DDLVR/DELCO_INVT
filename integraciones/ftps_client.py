"""
Cliente FTPS para integración con MoreApp

Este módulo maneja la descarga de archivos desde el servidor FTPS de MoreApp,
incluyendo archivos JSON con datos de formularios y fotos de evidencia.

Según TDR punto 6: "La información registrada en MoreApp debe ser incorporada 
automáticamente en la base de datos central."
"""

import os
import json
import logging
from ftplib import FTP_TLS, error_perm
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class FTPSClient:
    """Cliente para conectar y descargar archivos desde servidor FTPS de MoreApp"""
    
    def __init__(self):
        """Inicializar cliente FTPS con configuración desde settings"""
        self.host = getattr(settings, 'FTPS_HOST', '')
        self.port = getattr(settings, 'FTPS_PORT', 21)
        self.username = getattr(settings, 'FTPS_USERNAME', '')
        self.password = getattr(settings, 'FTPS_PASSWORD', '')
        self.base_path = getattr(settings, 'FTPS_BASE_PATH', '/')
        self.passive_mode = getattr(settings, 'FTPS_PASSIVE_MODE', True)
        self.connection = None
        
    def connect(self) -> bool:
        """
        Establecer conexión segura con servidor FTPS
        
        Returns:
            bool: True si conexión exitosa, False en caso contrario
        """
        try:
            logger.info(f"Conectando a FTPS: {self.host}:{self.port}")
            
            # Crear conexión FTP con TLS (FTPS)
            self.connection = FTP_TLS()
            self.connection.connect(self.host, self.port, timeout=30)
            self.connection.login(self.username, self.password)
            
            # Habilitar protección de datos (PROT P)
            self.connection.prot_p()
            
            # Configurar modo pasivo/activo
            self.connection.set_pasv(self.passive_mode)
            
            # Cambiar al directorio base
            if self.base_path and self.base_path != '/':
                self.connection.cwd(self.base_path)
            
            logger.info("Conexión FTPS establecida exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"Error al conectar a FTPS: {str(e)}")
            self.connection = None
            return False
    
    def disconnect(self):
        """Cerrar conexión FTPS de forma segura"""
        if self.connection:
            try:
                self.connection.quit()
                logger.info("Conexión FTPS cerrada")
            except:
                try:
                    self.connection.close()
                except:
                    pass
            finally:
                self.connection = None
    
    def list_files(self, remote_path: str = '.', pattern: str = '*') -> List[str]:
        """
        Listar archivos en directorio remoto
        
        Args:
            remote_path: Ruta en servidor FTPS
            pattern: Patrón de filtrado (ej: '*.json')
        
        Returns:
            Lista de nombres de archivos
        """
        if not self.connection:
            logger.error("No hay conexión FTPS activa")
            return []
        
        try:
            files = []
            self.connection.cwd(remote_path)
            
            # Obtener listado de archivos
            file_list = self.connection.nlst()
            
            for filename in file_list:
                # Filtrar por patrón si es necesario
                if pattern == '*' or filename.endswith(pattern.replace('*', '')):
                    files.append(filename)
            
            logger.info(f"Encontrados {len(files)} archivos en {remote_path}")
            return files
            
        except error_perm as e:
            logger.error(f"Error de permisos al listar {remote_path}: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error al listar archivos: {str(e)}")
            return []
    
    def download_file(self, remote_path: str, local_path: str) -> bool:
        """
        Descargar un archivo desde FTPS
        
        Args:
            remote_path: Ruta completa del archivo en servidor
            local_path: Ruta local donde guardar el archivo
        
        Returns:
            bool: True si descarga exitosa
        """
        if not self.connection:
            logger.error("No hay conexión FTPS activa")
            return False
        
        try:
            # Crear directorio local si no existe
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Descargar archivo en modo binario
            with open(local_path, 'wb') as local_file:
                self.connection.retrbinary(f'RETR {remote_path}', local_file.write)
            
            logger.info(f"Archivo descargado: {remote_path} -> {local_path}")
            return True
            
        except error_perm as e:
            logger.error(f"Error de permisos al descargar {remote_path}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error al descargar {remote_path}: {str(e)}")
            return False
    
    def download_json_files(self, remote_dir: str = 'json', 
                           local_dir: Optional[str] = None) -> List[Tuple[str, Dict]]:
        """
        Descargar todos los archivos JSON desde directorio de MoreApp
        
        Args:
            remote_dir: Directorio remoto con archivos JSON
            local_dir: Directorio local para guardar (opcional)
        
        Returns:
            Lista de tuplas (nombre_archivo, contenido_json)
        """
        if not local_dir:
            local_dir = os.path.join(settings.MEDIA_ROOT, 'ftps_downloads', 'json')
        
        os.makedirs(local_dir, exist_ok=True)
        
        # Listar archivos JSON
        json_files = self.list_files(remote_dir, '*.json')
        
        downloaded = []
        for filename in json_files:
            remote_path = f"{remote_dir}/{filename}"
            local_path = os.path.join(local_dir, filename)
            
            # Descargar archivo
            if self.download_file(remote_path, local_path):
                try:
                    # Leer y parsear JSON
                    with open(local_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    downloaded.append((filename, data))
                    logger.info(f"JSON procesado: {filename}")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Error al parsear JSON {filename}: {str(e)}")
                except Exception as e:
                    logger.error(f"Error al procesar {filename}: {str(e)}")
        
        logger.info(f"Descargados {len(downloaded)} archivos JSON")
        return downloaded
    
    def download_images(self, remote_dir: str = 'images',
                       local_dir: Optional[str] = None) -> List[str]:
        """
        Descargar archivos de evidencia fotográfica desde MoreApp
        
        Args:
            remote_dir: Directorio remoto con imágenes
            local_dir: Directorio local para guardar (opcional)
        
        Returns:
            Lista de rutas locales de archivos descargados
        """
        if not local_dir:
            local_dir = os.path.join(settings.MEDIA_ROOT, 'ftps_downloads', 'images')
        
        os.makedirs(local_dir, exist_ok=True)
        
        # Listar imágenes (jpg, png, jpeg)
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']
        image_files = []
        
        for ext in image_extensions:
            image_files.extend(self.list_files(remote_dir, ext))
        
        # Eliminar duplicados
        image_files = list(set(image_files))
        
        downloaded = []
        for filename in image_files:
            remote_path = f"{remote_dir}/{filename}"
            local_path = os.path.join(local_dir, filename)
            
            if self.download_file(remote_path, local_path):
                downloaded.append(local_path)
        
        logger.info(f"Descargadas {len(downloaded)} imágenes")
        return downloaded
    
    def download_all_moreapp_data(self) -> Dict[str, any]:
        """
        Descargar todos los datos disponibles desde MoreApp
        
        Según TDR: Obtener formularios JSON + evidencias fotográficas
        
        Returns:
            Diccionario con:
                - json_files: Lista de (filename, data)
                - images: Lista de rutas locales
                - timestamp: Fecha/hora de descarga
                - success: bool
        """
        result = {
            'json_files': [],
            'images': [],
            'timestamp': datetime.now(),
            'success': False,
            'errors': []
        }
        
        try:
            # Conectar
            if not self.connect():
                result['errors'].append('No se pudo establecer conexión FTPS')
                return result
            
            # Descargar JSONs
            try:
                result['json_files'] = self.download_json_files()
            except Exception as e:
                error_msg = f"Error descargando JSONs: {str(e)}"
                logger.error(error_msg)
                result['errors'].append(error_msg)
            
            # Descargar imágenes
            try:
                result['images'] = self.download_images()
            except Exception as e:
                error_msg = f"Error descargando imágenes: {str(e)}"
                logger.error(error_msg)
                result['errors'].append(error_msg)
            
            # Desconectar
            self.disconnect()
            
            # Marcar como exitoso si se descargó al menos algo
            result['success'] = len(result['json_files']) > 0 or len(result['images']) > 0
            
        except Exception as e:
            error_msg = f"Error general en descarga: {str(e)}"
            logger.error(error_msg)
            result['errors'].append(error_msg)
        
        return result


def download_from_moreapp() -> Dict[str, any]:
    """
    Función de conveniencia para descargar datos de MoreApp
    
    Returns:
        Resultado de download_all_moreapp_data()
    """
    client = FTPSClient()
    return client.download_all_moreapp_data()
