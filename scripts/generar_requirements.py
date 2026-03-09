# Script para generar requirements.txt con todas las dependencias
# Ejecutar: python scripts/generar_requirements.py

import subprocess
import sys
from pathlib import Path

def main():
    print("Generando requirements.txt...")
    print("-" * 60)
    
    # Verificar que estamos en un entorno virtual
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("⚠️  ADVERTENCIA: No pareces estar en un entorno virtual")
        print("   Es recomendable usar un entorno virtual")
        response = input("¿Continuar de todos modos? (s/n): ")
        if response.lower() != 's':
            print("Operación cancelada")
            return
    
    # Generar requirements.txt
    try:
        result = subprocess.run(
            ["pip", "freeze"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Escribir al archivo en Backend/ (un nivel arriba)
        requirements_path = Path(__file__).parent.parent / "requirements.txt"
        with open(requirements_path, 'w', encoding='utf-8') as f:
            f.write(result.stdout)
        
        print(f"✅ Archivo generado exitosamente: {requirements_path}")
        print()
        print("Contenido:")
        print("-" * 60)
        print(result.stdout)
        
        # Verificar dependencias importantes
        important_packages = [
            'Django',
            'djangorestframework',
            'python-dotenv',
            'mysqlclient',  # Para MySQL en producción
        ]
        
        print("-" * 60)
        print("Verificando dependencias importantes:")
        for package in important_packages:
            if package.lower() in result.stdout.lower():
                print(f"✅ {package} incluido")
            else:
                print(f"⚠️  {package} NO encontrado")
                if package == 'mysqlclient':
                    print(f"   → Instalar para producción: pip install mysqlclient")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error al ejecutar pip freeze: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    print()
    print("=" * 60)
    print("SIGUIENTE PASO:")
    print("1. Revisa el archivo requirements.txt")
    print("2. Si falta mysqlclient, instálalo: pip install mysqlclient")
    print("3. Ejecuta: python verificar_despliegue.py")
    print("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
