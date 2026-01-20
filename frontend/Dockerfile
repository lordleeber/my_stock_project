FROM node:20-alpine

WORKDIR /app

# 安裝 libc6-compat 以支援 Next.js 的 SWC 編譯器
RUN apk add --no-cache libc6-compat

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
