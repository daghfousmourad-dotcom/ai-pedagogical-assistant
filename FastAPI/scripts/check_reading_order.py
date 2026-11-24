import os
import sys

# Add the project root to sys.path
sys.path.append("/Volumes/MonSSD/pfe/test-microservices/FastAPI")

from services.core.navigator import SmartCourseNavigator

def check_order():
    mongo_id = "69c810dd139359198fc1aaf1"
    page_num = 6
    
    print(f"--- ANALYSE DE LA PAGE {page_num} DU PDF ---")
    nav = SmartCourseNavigator()
    words = nav.get_page_word_map(mongo_id, page_num, should_prefetch=False)
    
    if not words:
        print("❌ Aucun mot trouvé sur cette page.")
        return
        
    print(f"✅ Total : {len(words)} mots extraits.")
    print("\n[LES 10 PREMIERS MOTS (DANS L'ORDRE DES INDEX)]")
    for i in range(min(10, len(words))):
        w = words[i]
        # BBox format: [x0, y0, x1, y1]
        print(f"Index {i:2} | '{w['text']:15}' | y0: {w['bbox'][1]:.2f} | x0: {w['bbox'][0]:.2f}")

    # Vérification du tri vertical
    y_coords = [w['bbox'][1] for w in words]
    # Tolérance de 5 points pour le tri vertical (car on a utilisé round(y/5)*5)
    is_mostly_sorted_y = all(round(y_coords[i]/5)*5 <= round(y_coords[i+1]/5)*5 for i in range(len(y_coords)-1))
    
    if is_mostly_sorted_y:
        print("\n🏆 LE TRI SPATIAL EST OPÉRATIONNEL : Les mots suivent bien l'ordre du haut vers le bas.")
    else:
        print("\n⚠️ ATTENTION : Le tri vertical n'est pas parfait. Vérifiez les gros titres ou footers.")

if __name__ == "__main__":
    check_order()
