# 视图函数
import os
import time
from flask import Blueprint, request, g, current_app
from .forms import RegisterForm, LoginForm, UploadAvatarForm, EditSettingForm, UploadImageText, EditImageText, MessageForm
from models.auth import UserModel, ImageModel, ImageTextModel, MessageModel
from utils import restful
from exts import db
from hashlib import md5
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from flask_avatars import Identicon
from sqlalchemy import or_


bp = Blueprint('front', __name__, url_prefix='/api')


#  --钩子函数-- before_request:在执行视图函数之前，执行任何通过 @app.before_request 注册的钩子函数
@bp.before_request
@jwt_required(optional=True)
def front_before_request():
    if request.method == "OPTIONS":
        return
    # 从访问令牌中获取用户ID
    identity = get_jwt_identity()
    user = UserModel.query.filter_by(id=identity).first()
    if user:
        setattr(g, 'user', user)


# 格式化处理接口需要的数据
def export_data(imgtextmodel, imgs):
    filenames = [img.filename for img in imgs]
    item = {
        "id": imgtextmodel.id,
        "username": imgtextmodel.author.username,
        "user_id": imgtextmodel.author.id,
        "user_avatar": imgtextmodel.author.avatar,
        "title": imgtextmodel.title,
        "detail": imgtextmodel.detail,
        "filename": filenames
    }
    return item


# login 视图函数
@bp.post('/login')
def login_page():
    # 获取表单数据-验证数据-存入数据库
    form = LoginForm(request.form)
    if form.validate():
        password = form.password.data
        phone_number = form.phone_number.data
        user = UserModel.query.filter_by(phone_number=phone_number).first()
        if not user:  # 是否已经存在此号码
            return restful.params_error(message='手机号码或密码错误！')
        if not user.password_check(password):  # 密码与之前是否相同
            return restful.params_error(message='手机号码或密码错误！')
        # 创建访问令牌 token
        token = create_access_token(identity=user.id)  # identity 能识别用户的唯一标识符
        # user.image_text
        return restful.ok(message="登陆成功！", data={"token": token, "user": user.to_dict()})
    else:
        message = form.errors
        return restful.params_error(message=message)


# register 视图函数
@bp.post('/register')
def register_page():
    # 获取表单数据-验证数据-存入数据库
    form = RegisterForm(request.form)
    if form.validate():
        username = form.username.data
        phone_number = form.phone_number.data
        password = form.password.data
        identicon = Identicon()  # 自动生成头像
        filenames = identicon.generate(text=md5(phone_number.encode("utf-8")).hexdigest())
        avatar = filenames[1]
        # 存储在数据库中
        user = UserModel(username=username, password=password, phone_number=phone_number, avatar=avatar)
        db.session.add(user)
        db.session.commit()
        return restful.ok()
    else:
        message = form.errors
        return restful.params_error(message=message)


#  判断是否有cookie
# @bp.get('/is_cookie')
# def is_cookie():
#     # 获取当前cookie中的user_id(session加密后的) --> 数据库中查找该ID的用户信息 --> 提取出来放入全局变量中
#     if 'user_id' in session:
#         user_id = session.get('user_id')
#         user = UserModel.query.get(user_id)
#         setattr(g, 'user', user)
#         return restful.ok(data={"user": user.username})
#     else:
#         setattr(g, 'user', None)
#         return restful.ok(data={"user": None})


#  上传用户头像
@bp.post('/avatar/upload')
def upload_avatar():
    #  获取数据 -》form验证 -》存储在数据库
    print(request.files)
    form = UploadAvatarForm(request.files)
    if form.validate():
        image = form.image.data
        filename = image.filename
        # 图片路径解包 acb.jpg ==> (abc,jpg) 拿到图片后缀 (_,ext)  ext=>jpg后缀
        _, ext = os.path.splitext(filename)
        # 加密处理用户头像图片文件名，避免黑客或者用户图片重名
        filename = md5((filename + str(time.time())).encode('utf-8')).hexdigest() + ext
        # 添加图片到文件夹中（路径）
        image_path = os.path.join(current_app.config['AVATARS_SAVE_PATH'], filename)
        image.save(image_path)
        #
        g.user.avatar = filename
        db.session.commit()
        return restful.ok(data={"filename": filename})
    else:
        message = form.errors
        return restful.params_error(message=message)


#  用户个性信息修改
@bp.post('/user/setting')
def user_setting():
    form = EditSettingForm(request.form)
    if form.validate():
        username = form.username.data
        g.user.username = username  # 在全局变量中修改
        db.session.commit()
        return restful.ok(data={'username': username})  # 返回json数据
    else:
        return restful.params_error(message=form.errors)


#  上传图片
@bp.post('/upload/image')
def upload_image():
    form = UploadAvatarForm(request.files)
    if form.validate():
        image = form.image.data
        filename = image.filename
        _, ext = os.path.splitext(filename)
        # 加密后的图片文件
        filename = md5((filename + str(time.time())).encode('utf-8')).hexdigest() + ext
        # 存放路径
        image_path = os.path.join(current_app.config['POST_IMAGE_SAVE_PATH'], filename)
        image.save(image_path)

        return restful.ok(data={"filename": filename})
    else:
        message = form.errors
        return restful.params_error(message=message)


#  上传图片表单提交
@bp.post('/detail/image')
def detail_image():
    #   前端提交的数据结构 {title: '手绘', detail: '表情包', filenames:  ['c819d.png', 'de77e22f.png']}
    form = UploadImageText(request.form)

    if form.validate():
        title = form.title.data
        detail = form.detail.data
        # 提取 filenames ['c819d.png', 'de77e22f.png']
        filenames = []
        for key in request.form.keys():
            if key.startswith('filenames['):
                filenames.append(request.form[key])

        # 验证 filenames
        if not filenames:
            return restful.params_error(message="请上传图片！")
        # 存储标题和描述
        img_text = ImageTextModel(title=title, detail=detail, author_id=g.user.id)
        db.session.add(img_text)
        db.session.flush()  # 获取 img_text 的 id
        # 存储图片文件名
        for image in filenames:
            img = ImageModel(filename=image, text_id=img_text.id)
            db.session.add(img)

        db.session.commit()
        return restful.ok()
    else:
        return restful.params_error(message=form.errors)


# 首页--视图函数
@bp.route('/home')
def index():
    #  返回用户数据
    image_info_list = []
    image_text_s = ImageTextModel.query.order_by(ImageTextModel.create_time.desc()).all()
    # image_text_s ==》[<ImageTextModel 5>, <ImageTextModel 9>] 需要处理成下面格式
    # [{'username': '小红', 'title': '自然', 'detail': '生活', 'filename': ['4b8c2fe.jpg', '71487.jpeg']},
    # {'username': 'shu 属鼠', 'title': '油画', 'detail': '手绘', 'filename': ['b40810.jpg', 'ef5376a9b.JPG']},
    # {'username': 'shu 属鼠', 'title': '表情包', 'detail': '可爱手绘', 'filename': ['d43af.png', 'dd86.png']}]
    for image_text in image_text_s:
        images = image_text.images
        # 处理数据结构的自定义函数
        item = export_data(image_text, images)
        image_info_list.append(item)
    return restful.ok(data=image_info_list)


# 用户详情页展示（当前用户的全部照片）
@bp.route('user/picture/<user_id>')
def user_picture(user_id):
    try:
        user = UserModel.query.get(user_id)
    except Exception as e:
        return restful.params_error(message="改用户不存在！")
    # all 图片， 图片数量， 头像， 姓名
    user_img_list = []

    text_list = user.image_text  # 当前用户的详情列表 [<ImageTextModel 8>, <ImageTextModel 9>]
    for text in text_list:
        image_list = text.images  # 详情下图片列表  [<ImageModel 1>, <ImageModel 2>]
        filenames = [image.filename for image in image_list]

        items = {
            "title": text.title,
            "detail": text.detail,
            "filename": filenames,
            "id": text.id
        }

        user_img_list.append(items)

    return restful.ok(data={"avatar": user.avatar,
                            "user_join_time": user.join_time,
                            "username": user.username,
                            "user_img_list": user_img_list})


# 删除图片专辑
@bp.post('/delete/img')
def delete_post_image():
    post_id = request.form.get('id')
    if not post_id:
        return restful.params_error('没有传入删除图片的ID！')
    try:
        post = ImageTextModel.query.get(post_id)
    except Exception as e:
        return restful.params_error(message="此专辑不存在！")
    db.session.delete(post)
    db.session.commit()
    return restful.ok(message="专辑删除成功！")


# 修改图片专辑
@bp.post('/update/img')
def update_post_image():
    print(request.form)
    form = EditImageText(request.form)
    if form.validate():
        # ----- 验证 filenames数组
        # 提取数组 ('imgs[0]', '7c322.png') ，('imgs[1]', '595b9.png')
        filenames = []  # ==> ['7c322.png', '595b9.png' ]
        for key in request.form.keys():  # request.form.keys() ==> dict_keys(['title', 'detail', 'imgs[0]', 'imgs[1]'])
            if key.startswith('imgs['):
                filenames.append(request.form[key])
        if not filenames:
            return restful.params_error('图片不能为空！')

        #  ----在数据库中查询 是否存在---
        post_id = form.post_id.data
        try:
            post_img = ImageTextModel.query.get(post_id)
        except Exception as e:
            return restful.params_error("没有该专辑！")
        #  --- 重新赋值 修改图片信息---
        title = form.title.data
        detail = form.detail.data

        post_img.title = title
        post_img.detail = detail
        for img in post_img.images:  # post_img.images ==》 [<ImageModel 18>, <ImageModel 19>]
            if img.filename not in filenames:
                db.session.delete(img)
        db.session.commit()
        return restful.ok()
    else:
        return restful.params_error(form.errors)


# 搜索关键字
@bp.route('/search/img')
def search_img():
    q = request.args.get("q")  # /search/img?q=xxx 路径传参数

    result = ImageTextModel.query.filter(or_(ImageTextModel.title.contains(q), ImageTextModel.detail.contains(q))).all()
    image_info_list = []
    print("---- result ----", result)
    # result [<ImageTextModel 5>, <ImageTextModel 9>]
    if len(result) > 0:
        for imgTextmodel in result:
            images = imgTextmodel.images
            # 函数
            item = export_data(imgTextmodel, images)
            image_info_list.append(item)
        return restful.ok(data=image_info_list)
    else:
        return restful.params_error('没有找到相关的图片！')


#  搜索用户名
@bp.route('/search/username')
def search_username():  # /search/username?username=xxx
    username = request.args.get('username')
    users = UserModel.query.filter(UserModel.username.contains(username)).all()
    if len(users) < 1:  # [<UserModel 8Bg3erTghTdYRSJTqwd9pA>, <UserModel VrovN8QYvZxY6zmyFm7rCP>]
        return restful.params_error('没有找到相关的用户！')
    print("---user---", users)
    user_info = []
    for user in users:
        item = {
            'uid': user.id,
            'username': user.username,
            "avatar": user.avatar
        }
        user_info.append(item)
    return restful.ok(data=user_info)


# 提交留言
@bp.post('/send/message')
def send_message():
    print("---message---", request.form)
    form = MessageForm(request.form)
    if form.validate():
        msg = form.msg.data
        message = MessageModel(msg=msg)
        db.session.add(message)
        db.session.commit()
        return restful.ok()
    else:
        return restful.params_error(form.errors)
