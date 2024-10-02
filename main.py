from fastapi import FastAPI, Request, HTTPException, status, Depends
from tortoise.contrib.fastapi import register_tortoise
from models import *
from authentication import (get_hashed_password, very_token, token_generator)

from tortoise.signals import post_save
from typing import List, Optional, Type
from tortoise import BaseDBAsyncClient
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from emails import *
from fastapi.security import (OAuth2PasswordBearer, OAuth2PasswordRequestForm)
from fastapi import File, UploadFile
import secrets
from fastapi.staticfiles import StaticFiles
from PIL import Image





app = FastAPI()
oauth2_schema = OAuth2PasswordBearer(tokenUrl = 'token')


app.mount("/static",StaticFiles(directory="static"),name="static")



@app.post('/token')
async def generate_token(request_form:OAuth2PasswordRequestForm = Depends()):
    token = await token_generator(request_form.username, request_form.password)
    return {"access_token" : token , "token_type": "bearer"}


async def get_current_user(token:str = Depends(oauth2_schema)):
   try:
        payload = jwt.decode(token,config_credentials['SECRET'], algorithms=["HS256"])
        user = await User.get(id = payload.get['id'])
        return user
   except:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate":"Bearer"}
        )
    


@app.post("/user/me")
async def user_login(user : user_pydantic = Depends(get_current_user)):
    business = await Business.get(owner = user)
    logo = business.logo
    logo_path = "localhost:8000/static/images/"+logo

    return {
        "status":"ok",
        "data":{
            "username":user.username,
            "email":user.email,
            "verified":user.is_verified,
            "joined_date": user.join_date.strftime("%b %d %Y"),
            "logo": logo_path
        }
    }


@post_save(User)
async def create_business(
    sender:"Type[User]",
    instance: User,
    created:bool,
    using_db: "Optional[BaseDBAsyncClient]",
    update_fields:List[str]
)-> None:
    if created :
        business_obj = await Business.create(
            business_name = instance.username, owner = instance
        )
        await business_pydantic.from_tortoise_orm(business_obj)
        await send_email([instance.email], instance)


@app.post("/registration")
async def  user_registration(user: user_pydanticIn):
    user_info = user.dict(exclude_unset=True)
    user_info["password"] = get_hashed_password(user_info["password"])
    user_obj = await User.create(**user_info)
    new_user = await user_pydantic.from_tortoise_orm(user_obj)
    return {
        "status": "ok",
        "data": f"Hello {new_user.username}, thanks for choosing our services. please check your email inbox and click on the link to confirm your registartion."
    }


templates= Jinja2Templates(directory="templates")
@app.get("/verification", response_class=HTMLResponse)
async def email_verification(request:Request, token:str):
    user = await very_token(token)
    if user and not user.is_verified:
        user.is_verified = True
        await user.save()
        return templates.TemplateResponse("verification.html", {"request": request, "username":user.username})

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid token or expired token",
        headers={"WWW-Authenticate":"Bearer"}
    )


@app.get("/")
def index():
    return {"message": "hello world"}



@app.url_path_for("/uploadfile/profile")
async def create_upload_file(file:UploadFile=File(...),
                             user : user_pydantic = Depends(get_current_user)):
    
    FILEPATH = "./static/images/"
    filename = file.filename
    extension = filename.split(".")

    if extension not in ["jpg", "png"]:
        return {
            "status": "error",
            "detail": "File extension not allowed"
        }
    token_name = secrets.token_hex(10)+"."+ extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()

    with open(generated_name, "wb") as file:
        file.write(file_content)


    img = Image.open(generated_name)
    img = img.resize(size = (200, 200))
    img.save(generated_name)


    file.close()

    business = await Business.get(owner = user)
    owner = await business.owner

    if owner == user:
        business.logo = token_name
        await business.save()
        file_url = "localhost:8000" + generated_name[1:]

        return {
            "status": "ok",
            "filename": file_url
        }

    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated to perform this action",
            headers={"WWW-Authenticate":"Bearer"}
        )



@app.post("/uploadfile/product/{id}")
async def create_upload_file(id: int, file: UploadFile = File(...),
                             user: user_pydantic = Depends(get_current_user)):
    
    FILEPATH = "./static/images/"
    filename = file.filename
    extension = filename.split(".")

    if extension not in ["jpg", "png"]:
        return {
            "status": "error",
            "detail": "File extension not allowed"
        }
    token_name = secrets.token_hex(10)+"."+ extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()

    with open(generated_name, "wb") as file:
        file.write(file_content)


    img = Image.open(generated_name)
    img = img.resize(size = (200, 200))
    img.save(generated_name)


    file.close()

    product = await Product.get(id = id)
    business = await product.business
    owner = await business.owner

    if owner == user:
        product.product_image = token_name
        await product.save()
        file_url = "localhost:8000" + generated_name[1:]

        return {
            "status": "ok",
            "filename": file_url
        }

    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated to perform this action",
            headers={"WWW-Authenticate":"Bearer"}
        )



@app.post("/products")
async def add_new_product(product: product_pydanticIn,
                          user : user_pydantic = Depends(get_current_user)):
    
    product = product.dict(exclude_unset = True)
    if product["original_price"] > 0:
        product["percentage_discount"] = ((product["original_price"]- product["new_price"]) / product["original_price"]) * 100
    
        product_obj = await Product.create(**product, business = user)
        product_obj = await product_pydantic.from_tortoise_orm(product_obj)

        return {
            "status": "ok",
            "data" : product_obj
        }
    
    else:
        return {
            "status": "error"
        }


@app.get("/product")
async def get_product():
    response = await product_pydantic.from_queryset(Product.all())
    return {
        "status": "ok",
        "data": response
    }




@app.get("/product/{id}")
async def get_product(id: int):
    product = await Product.get(id = id)
    business =  await product.business
    owner = await business.owner
    response = product_pydantic.from_queryset_single(Product.get(id = id))

    return {
        "status": "ok",
        "data": {
            "product_details" : response,
            "business_details" : {
                "name": business.business_name,
                "city": business.city,
                "region": business.region,
                "description": business.business_description,
                "logo":business.logo,
                "owner_id" : owner.id,
                "email" : owner.email,
                "join_date": owner.join_date.strftime("%b %d %Y") 
            }
        }
    }



@app.delete("/product/{id}")
async def delete_product(id: int, user : user_pydantic = Depends(get_current_user)):
    product = await Product.get(id = id)
    business = await product.business
    owner = await business.owner

    if user == owner:
        product.delete()

        return {"status" : "ok"}
    
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated to perform this action",
            headers={"WWW-Authenticate":"Bearer"}
        )
    


@app.put("/product/{id}")
async def update_product(id: int,
                         update_info: product_pydanticIn,
                         user: user_pydantic = Depends(get_current_user)):
    
    product = await Product.get(id = id)
    business = await product.business
    owner = await business.owner

    update_info = update_info.dict(exclude_unset=True)
    update_info["date_published"] = datetime.utcnow()

    if user == owner and update_info["original_price"] > 0:
        update_info["percentage_discount"] = ((update_info["original_price"] - update_info["new_price"]) / update_info["original_price"]) * 100

        await product.update_from_dict(update_info)
        await product.save()
        response = await product_pydantic.from_tortoise_orm(product)

        return {
            "status": "ok",
            "data" : response
        }
    
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated to perform this action or invalid user input",
            headers={"WWW-Authenticate":"Bearer"}
        )


@app.put("/business/{id}")
async def update_business(id: int,
                          update_info: business_pydanticIn,
                          user: user_pydantic = Depends(get_current_user)):
    
    update_business = update_business.dict()

    business = await Business.get(id = id)
    business_owner = await business.owner

    if user == business_owner:
        await business.update_from_dict(update_business)
        await business.save()
        response = await business_pydantic.from_tortoise_orm(business)

        return {
            "status": "ok",
            "data" : response
        }
    
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated to perform this action",
            headers={"WWW-Authenticate":"Bearer"}
        )


register_tortoise(
    app,
    db_url="mysql://root:1234@localhost:3306/e_commerce",
    modules={"models":["models"]},
    generate_schemas=True,
    add_exception_handlers=True
)
