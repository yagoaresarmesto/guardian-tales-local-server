import { itemCatalog } from "/catalog-picker.js";

export function equipmentCatalog(types, tile, drawArt, onAdded) {
  return itemCatalog({section: "equipment", types, tile, drawArt, onAdded});
}
