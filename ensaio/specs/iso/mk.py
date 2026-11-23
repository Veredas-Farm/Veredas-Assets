import json,sys
ids={"par":"5fdd0c11639b","jogo":"dd41de2d0381","kit":"4f8942dd027a","ipe":"5e73b7aaab98","pequi":"a9a9f900c291","baru":"be5237c3f1f7"}
def w(exp,name,base,prompt,denoise,template="moss-pixel",extra=None):
    s={"name":name,"template":template,"base":ids[base],"set":{"prompt":prompt,"denoise":str(denoise)}}
    if extra: s["set"].update(extra)
    json.dump([s],open(f"specs/iso/{exp}.json","w"),indent=1,ensure_ascii=False)
