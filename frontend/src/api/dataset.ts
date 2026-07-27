import { apiData } from "./client"
export interface DatasetItem { name:string; relative_path:string; category:string; caption:string; caption_exists:boolean; tags:string[]; image_url:string }
export interface DatasetScan { root:string; total:number; items:DatasetItem[]; tags:{tag:string;count:number}[]; categories:{name:string;value:string;count:number}[] }
export interface ChangedItem { image:string; caption:string; caption_exists:boolean; tags:string[] }
const post = <T>(path:string, body:unknown) => apiData<T>(path,{method:"POST",body:JSON.stringify(body)})
export const datasetApi = { scan:(path:string)=>post<DatasetScan>("/api/dataset-editor/scan",{path}), save:(root:string,image:string,caption:string)=>post<ChangedItem>("/api/dataset-editor/caption",{root,image,caption}), batch:(body:Record<string,unknown>)=>post<{changed:number;items:ChangedItem[]}>("/api/dataset-editor/batch",body), undo:(root:string)=>post<{changed:number;items:ChangedItem[]}>("/api/dataset-editor/undo",{root}), redo:(root:string)=>post<{changed:number;items:ChangedItem[]}>("/api/dataset-editor/redo",{root}) }
